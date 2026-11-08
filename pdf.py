#!/usr/bin/env python3
"""Extract CAMS Consolidated Account Statement into three linked CSVs.

users.csv          personal details (1 row per statement)
schemes.csv        one row per folio/scheme  -> user_id
transactions.csv   one row per txn           -> scheme_id
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from  mf_api import filter_mf_search_based_on_isin 
from cuid2 import cuid_wrapper
from db import Session
from queries import create_user, create_scheme
from datetime import datetime



DATE_RE = r"\d{2}-[A-Za-z]{3}-\d{4}"
NUM_RE = r"[\d,]+\.?\d*"

EMAIL_RE = re.compile(r"Email Id:\s*(\S+)", re.I)
PERIOD_RE = re.compile(rf"({DATE_RE})\s+To\s+({DATE_RE})", re.I)
PHONE_RES_RE = re.compile(r"Phone Res:\s*(\S+)", re.I)
MOBILE_RE = re.compile(r"Mobile:\s*(\S+)", re.I)

FOLIO_RE = re.compile(
    r"Folio No:\s*([0-9]+(?:\s*/\s*[0-9]+)?)"
    r"(?:.*?PAN:\s*([A-Z]{5}[0-9]{4}[A-Z]))?"
    r"(?:.*?KYC:\s*(\S+))?"
    r"(?:.*?PAN:\s*(\S+))?",
    re.I,
)
KYC_ONLY_RE = re.compile(r"KYC:\s*(\S+)\s+PAN:\s*(\S+)", re.I)
PAN_INLINE_RE = re.compile(r"\bPAN:\s*([A-Z]{5}[0-9]{4}[A-Z])\b", re.I)
ISIN_RE = re.compile(
    r"(?P<code>[A-Z0-9]{3,})-(?P<name>.+?)\s*-\s*ISIN:\s*(?P<isin>[A-Z0-9]+)"
    r"(?:\(Advisor:\s*(?P<advisor>[^)]+)\))?"
    r"(?:\s*Registrar\s*:\s*(?P<registrar>\S+))?",
    re.I,
)
CLOSING_RE = re.compile(
    rf"Closing Unit Balance:\s*(?P<units>{NUM_RE})"
    rf"(?:\s+NAV on (?P<nav_date>{DATE_RE}):\s*INR\s*(?P<nav>{NUM_RE}))?"
    rf"(?:\s+Total Cost Value:\s*(?P<cost>{NUM_RE}))?"
    rf"(?:\s+Market Value on (?P<mv_date>{DATE_RE}):\s*INR\s*(?P<mv>{NUM_RE}))?",
    re.I,
)
CLOSING_NAV_RE = re.compile(
    rf"NAV on (?P<nav_date>{DATE_RE}):\s*INR\s*(?P<nav>{NUM_RE})", re.I
)
CLOSING_COST_RE = re.compile(rf"Total Cost Value:\s*(?P<cost>{NUM_RE})", re.I)
CLOSING_MV_RE = re.compile(
    rf"Market Value on (?P<mv_date>{DATE_RE}):\s*INR\s*(?P<mv>{NUM_RE})", re.I
)
TEXT_MARKERS = (
    "Email Id:",
    "Folio No:",
    "Closing Unit Balance",
    "PORTFOLIO SUMMARY",
    "ISIN:",
    "Consolidated Account Statement",
)
TXN_RE = re.compile(
    rf"^(?P<date>{DATE_RE})\s+"
    rf"(?P<desc>.+?)\s+"
    rf"(?P<amount>{NUM_RE})"
    rf"(?:\s+(?P<units>{NUM_RE})\s+(?P<price>{NUM_RE})\s+(?P<balance>{NUM_RE}))?\s*$"
)
AMC_LINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &./'-]*Mutual Fund$|^Quant MF$", re.I)
NOISE_RE = re.compile(
    r"^(Date\s+Transaction|Consolidated Account Statement|CAMSCASWS|"
    r"Page \d+ of \d+|PORTFOLIO SUMMARY|Current Load Structure|"
    r"\"Please ensure|Entry [Ll]oad|Exit [Ll]oad|Nominee \d+:|"
    r"Opening Unit Balance:|This Consolidated|friendly initiative|"
    r"investments\.|entered by you|is common to|consolidate all|"
    r"If you find|registered your|This statement may|holdings\.|"
    r"Cost Value|Market Value|\(INR\)|Mutual Fund\s*$|"
    r"^\s*Total\s+|^\d{2}-[A-Za-z]{3}-\d{4}\s+To\s+)",
    re.I,
)


def parse_number(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace(",", "")


def extract_text_native(pdf_path: Path) -> str:
    """Extract embedded text via pdftotext -layout, then pdfplumber."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def is_text_usable(text: str) -> bool:
    """True when native extract has enough CAS markers to parse."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text or "")
    if len(cleaned.strip()) < 200:
        return False
    lower = cleaned.lower()
    hits = sum(1 for marker in TEXT_MARKERS if marker.lower() in lower)
    return hits >= 2

def cuid_generator() -> str:

    create_cuid = cuid_wrapper()
    return  create_cuid()
    


def extract_text(
    pdf_path: Path,
    *,
    mode: str = "auto",
    ocr_dpi: int = 300,
) -> tuple[str, str]:
    """Return (text, source) where source is 'text' or 'ocr'.

    mode:
      auto — try native text first; OCR if scanned / empty
      text — native only
      ocr  — force OCR (find_ocr.extract_text_ocr)
    """
    mode = mode.lower().strip()
    if mode not in {"auto", "text", "ocr"}:
        raise ValueError(f"Unknown extract mode: {mode}")

    if mode == "ocr":
        from find_ocr import extract_text_ocr

        print("Using OCR extraction…", file=sys.stderr)
        return extract_text_ocr(pdf_path, dpi=ocr_dpi, progress=True), "ocr"

    native = extract_text_native(pdf_path)
    if mode == "text":
        return native, "text"

    if is_text_usable(native):
        return native, "text"

    from find_ocr import extract_text_ocr

    print(
        "Little/no selectable text found — falling back to OCR…",
        file=sys.stderr,
    )
    return extract_text_ocr(pdf_path, dpi=ocr_dpi, progress=True), "ocr"


def left_column(line: str, split_at: int = 72) -> str:
    """Keep the investor-facing left column from dual-column header lines."""
    if len(line) <= split_at:
        return line.rstrip()
    return line[:split_at].rstrip()


@dataclass
class User:
    user_id: str
    name: str = ""
    email: str = ""
    phone_res: str = ""
    mobile: str = ""
    pan: str = ""
    address: str = ""
    statement_from: str = ""
    statement_to: str = ""


@dataclass
class Scheme:
    scheme_id: str
    user_id: str
    amc_name: str = ""
    folio_no: str = ""
    holder_name: str = ""
    scheme_name: str = ""
    scheme_code: str = ""
    isin: str = ""
    pan: str = ""
    closing_units: str = "" # Closing unit balance (lot size)
    nav_date: str = ""
    nav_inr: str = ""
    total_cost_value_inr: str = "" # Total cost value (investment amount)
    market_value_inr: str = "" # Market value (current value)
    scheme_type : str = ""
    scheme_category : str = ""
    sub_scheme_category : str = ""



@dataclass
class Transaction:
    transaction_id: str
    scheme_id: str
    date: str
    description: str
    amount_inr: str = ""
    units: str = ""
    price_inr: str = ""
    unit_balance: str = ""


@dataclass
class ParseResult:
    user: User
    schemes: list[Scheme] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)


def _trim_boilerplate(value: str) -> str:
    """Drop right-column CAS boilerplate that OCR merges onto personal lines."""
    cut_markers = (
        "This Consolidated",
        "balances and valuation",
        "friendly initiative",
        "investments. The consolidation",
        "PORTFOLIO SUMMARY",
    )
    out = value
    for marker in cut_markers:
        idx = out.find(marker)
        if idx > 0:
            out = out[:idx]
    return out.strip(" ,;-")


def parse_personal(text: str) -> User:
    email_m = EMAIL_RE.search(text)
    period_m = PERIOD_RE.search(text)
    phone_m = PHONE_RES_RE.search(text)
    mobile_m = MOBILE_RE.search(text)

    lines = text.splitlines()
    name = ""
    address_parts: list[str] = []

    # Personal block sits between Email Id and Phone Res / PORTFOLIO SUMMARY.
    capturing = False
    for raw in lines:
        line = left_column(raw)
        if not capturing:
            if EMAIL_RE.search(raw):
                capturing = True
            continue
        if (
            PHONE_RES_RE.search(raw)
            or MOBILE_RE.search(raw)
            or "PORTFOLIO SUMMARY" in raw.upper()
        ):
            break
        cleaned = _trim_boilerplate(line.strip())
        if not cleaned:
            continue
        if NOISE_RE.search(cleaned):
            continue
        if not name:
            name = cleaned
        else:
            address_parts.append(cleaned)

    user = User(
        user_id=cuid_generator(),
        name=name,
        email=email_m.group(1) if email_m else "",
        phone_res=phone_m.group(1) if phone_m else "",
        mobile=mobile_m.group(1) if mobile_m else "",
        address=", ".join(address_parts),
        statement_from=period_m.group(1) if period_m else "",
        statement_to=period_m.group(2) if period_m else "",
    )
    return user


def is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if NOISE_RE.search(s):
        return True
    if s.startswith("***") and "Stamp Duty" not in s and not re.match(DATE_RE, s):
        # Non-dated advisory lines that start mid-page; dated *** stay for txn parse.
        return False
    return False


def _start_scheme(
    schemes: list[Scheme],
    user: User,
    *,
    amc_name: str,
    folio_no: str = "",
    pan: str = "",
    kyc_status: str = "",
    pan_status: str = "",
    scheme_type: str = "",
    scheme_category : str = "",
    sub_scheme_category : str = "",
    nav_date : str = "",
    nav_inr : str = "",
    holder_name: str = "",
) -> Scheme:
    scheme = Scheme(
        scheme_id=cuid_generator(),
        user_id=user.user_id,
        amc_name=amc_name,
        folio_no=folio_no,
        pan=pan.upper() if pan else "",
        holder_name=holder_name,
        scheme_type=scheme_type,
        scheme_category=scheme_category,
        sub_scheme_category=sub_scheme_category,
        nav_date=nav_date,
        nav_inr=nav_inr,
    )
    schemes.append(scheme)
    if pan and not user.pan:
        user.pan = scheme.pan
    return scheme


def clean_scheme_name(name: str) -> str:
    """Drop parenthetical notes like (Formerly …) and (Non-Demat)."""
    cleaned = re.sub(r"\([^)]*\)", "", name or "")
    return re.sub(r"\s+", " ", cleaned).strip(" -")


def _apply_isin(scheme: Scheme, isin_m: re.Match[str]) -> None:
    scheme.scheme_code = isin_m.group("code")
    scheme.scheme_name = clean_scheme_name(isin_m.group("name"))
    scheme.isin = isin_m.group("isin").upper()
    scheme.advisor = (isin_m.group("advisor") or "").strip()
    scheme.registrar = (isin_m.group("registrar") or "").strip()


def _closing_complete(scheme: Scheme) -> bool:
    return bool(
        scheme.closing_units
        and scheme.nav_inr
        and scheme.total_cost_value_inr
        and scheme.market_value_inr
    )


def parse_schemes_and_txns(text: str, user: User) -> tuple[list[Scheme], list[Transaction]]:
    schemes: list[Scheme] = []
    transactions: list[Transaction] = []

    current_amc = ""
    current: Scheme | None = None
    pending_kyc = ("", "")
    awaiting_holder = False
    awaiting_scheme = False
    txn_seq = 0

    # Prefer folio start; for OCR fall back to first ISIN / KYC block.
    start_idxs = [
        i
        for i in (
            text.find("Folio No:"),
            text.find("ISIN:"),
            text.lower().find("kyc:"),
        )
        if i >= 0
    ]
    start = min(start_idxs) if start_idxs else -1
    if start >= 0:
        prefix = text[:start].splitlines()
        keep_from = max(0, len(prefix) - 8)
        body = "\n".join(prefix[keep_from:]) + "\n" + text[start:]
    else:
        body = text

    for raw in body.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        # Page chrome / table headers / OCR page markers.
        if re.match(r"^Date\s+Transaction", stripped):
            continue
        if re.match(r"^--- Page \d+", stripped):
            continue
        if re.match(r"^Consolidated Account Statement", stripped):
            continue
        if re.match(r"^CAMSCASWS", stripped) or re.match(r"^Page \d+ of \d+", stripped):
            continue
        if re.match(rf"^{DATE_RE}\s+To\s+{DATE_RE}", stripped):
            continue
        if stripped in {"(INR)", "Amount", "Units", "Price", "Unit", "Balance"}:
            continue

        amc_m = AMC_LINE_RE.match(stripped)
        if amc_m and "Folio No:" not in stripped and "ISIN:" not in stripped:
            current_amc = stripped
            continue

        folio_m = FOLIO_RE.search(stripped)
        if folio_m and "Folio No:" in stripped:
            current = _start_scheme(
                schemes,
                user,
                amc_name=current_amc,
                folio_no=re.sub(r"\s+", "", folio_m.group(1)),
                pan=folio_m.group(2) or "",
                kyc_status=folio_m.group(3) or pending_kyc[0],
                pan_status=folio_m.group(4) or pending_kyc[1],
            )
            pending_kyc = ("", "")
            awaiting_holder = True
            awaiting_scheme = False
            continue


 
        # OCR often loses Folio/PAN and only keeps "KYC: OK PAN: OK".
        kyc_m = KYC_ONLY_RE.search(stripped)
        if kyc_m and "Folio No:" not in stripped and "ISIN:" not in stripped:
            pending_kyc = (kyc_m.group(1), kyc_m.group(2))
            
            pan_m = PAN_INLINE_RE.search(stripped)
            if current is None or current.isin:
                current = _start_scheme(
                    schemes,
                    user,
                    amc_name=current_amc,
                    pan=pan_m.group(1) if pan_m else "",
                    kyc_status=pending_kyc[0],
                    pan_status=pending_kyc[1],
                )
                awaiting_holder = True
                awaiting_scheme = False
                  
            else:
                current.kyc_status = current.kyc_status or pending_kyc[0]
                current.pan_status = current.pan_status or pending_kyc[1]
                if pan_m and not current.pan:
                    current.pan = pan_m.group(1).upper()
                    if not user.pan:
                        user.pan = current.pan

                        
            continue



        isin_m = ISIN_RE.search(stripped)
        if isin_m:
            # New scheme via ISIN when OCR skipped folio header, or fill current.
            if current is None or (current.isin and current.isin != isin_m.group("isin").upper()):
                current = _start_scheme(
                    schemes,
                    user,
                    amc_name=current_amc,
                    kyc_status=pending_kyc[0],
                    pan_status=pending_kyc[1],
                )
                pending_kyc = ("", "")
            _apply_isin(current, isin_m)
            awaiting_holder = False
            awaiting_scheme = False

            continue

        if current is None:
            continue

        # Closing summary — may be split across OCR lines/pages.
        closing_m = CLOSING_RE.search(stripped)
        if closing_m:
            current.closing_units = parse_number(closing_m.group("units"))
            if closing_m.group("nav_date"):
                current.nav_date = closing_m.group("nav_date")
                current.nav_inr = parse_number(closing_m.group("nav"))
            if closing_m.group("cost"):
                current.total_cost_value_inr = parse_number(closing_m.group("cost"))
            if closing_m.group("mv_date"):
                current.market_value_date = closing_m.group("mv_date")
                current.market_value_inr = parse_number(closing_m.group("mv"))
            if _closing_complete(current):
                current = None
                awaiting_holder = False
                awaiting_scheme = False
            continue

        if current.closing_units and not _closing_complete(current):
            nav_m = CLOSING_NAV_RE.search(stripped)
            if nav_m:
                current.nav_date = nav_m.group("nav_date")
                current.nav_inr = parse_number(nav_m.group("nav"))
            cost_m = CLOSING_COST_RE.search(stripped)
            if cost_m:
                current.total_cost_value_inr = parse_number(cost_m.group("cost"))
            mv_m = CLOSING_MV_RE.search(stripped)
            if mv_m:
                current.market_value_date = mv_m.group("mv_date")
                current.market_value_inr = parse_number(mv_m.group("mv"))
            if nav_m or cost_m or mv_m:
                if _closing_complete(current):
                    current = None
                    awaiting_holder = False
                    awaiting_scheme = False
                continue

        if awaiting_holder:
            if "ISIN:" in stripped:
                awaiting_holder = False
                awaiting_scheme = True
            elif stripped.startswith("Nominee") or KYC_ONLY_RE.search(stripped):
                continue
            else:
                # Avoid treating AMC / noise as holder name.
                if not AMC_LINE_RE.match(stripped) and not NOISE_RE.search(stripped):
                    current.holder_name = stripped
                awaiting_holder = False
                awaiting_scheme = True
                continue

        if awaiting_scheme:
            if not stripped.startswith("Nominee") and "Opening Unit" not in stripped:
                combined = (
                    f"{current.scheme_name} {stripped}".strip()
                    if current.scheme_name
                    else stripped
                )
                print("beofre adding awaiting")
                current.scheme_name = clean_scheme_name(combined)

            continue

        if stripped.startswith("Nominee") or "Openi/ng Unit Balance:" in stripped:
            continue

        txn_m = TXN_RE.match(stripped)
        if txn_m:
            txn_seq += 1
            transactions.append(
                Transaction(
                    transaction_id=f"T{cuid_generator()}",
                    scheme_id=current.scheme_id,
                    date=txn_m.group("date"),
                    description=re.sub(r"\s+", " ", txn_m.group("desc")).strip(" -"),
                    amount_inr=parse_number(txn_m.group("amount")),
                    units=parse_number(txn_m.group("units")),
                    price_inr=parse_number(txn_m.group("price")),
                    unit_balance=parse_number(txn_m.group("balance")),
                )
            )
            continue

        # Dated description without amounts (OCR often splits amount onto next page).
        note_m = re.match(
            rf"^({DATE_RE})\s+(.+?)\s*$",
            stripped,
        )
        if note_m and not re.match(r"^\d", note_m.group(2)):
            desc = re.sub(r"\s+", " ", note_m.group(2)).strip()
            if desc and not desc.lower().startswith(("page ", "cams", "kfintech")):
                txn_seq += 1
                transactions.append(
                    Transaction(
                        transaction_id=f"T{txn_seq:05d}",
                        scheme_id=current.scheme_id,
                        date=note_m.group(1),
                        description=desc,
                    )
                )

    return schemes, transactions


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def update_nav_details(schemes : list[Scheme]) -> list[Scheme]:
    schemes: list[Scheme] = schemes
    for scheme in schemes:
        print(scheme.scheme_name, f"isin is {scheme.isin}")
        print()
        if scheme.scheme_name:
            q = re.sub(r'(?i)(?<=fund).*', '', scheme.scheme_name).strip()
            new_nav_data = filter_mf_search_based_on_isin(q, scheme.isin)
            print("the new nav data", new_nav_data)
            print()
            scheme.scheme_code = new_nav_data['meta']['scheme_code']
            scheme.scheme_type = new_nav_data['meta']['scheme_type']
            scheme.scheme_category = new_nav_data['meta']['scheme_category']
            scheme.sub_scheme_category = new_nav_data['meta']['sub_scheme_category']
            scheme.nav_date = new_nav_data['data'][0]['date']
            scheme.nav_inr = new_nav_data['data'][0]['nav']
            

    return schemes



def save_all_in_db( user :User, schemes : list[Scheme],transactions : list[Transaction]):
    
    with Session() as db:

        create_user(
            db=db,
            id=user.user_id,
            name= user.name, 
            email= user.email,
            pan=user.pan,
            address=user.address,
            phone_no = user.phone_res if user.phone_res else user.mobile,
            statement_from = datetime.strptime(user.statement_from, "%d-%b-%Y"),
            statement_to = user.statement_to

        )
        for scheme in schemes:
            create_scheme(
                db=db,
                id= scheme.scheme_id,
                user_id= scheme.user_id, 
                amc_name = scheme.amc_name,
                folio_no= scheme.amc_name,
                holder_name= scheme.holder_name,
                scheme_name= scheme.scheme_name,
                scheme_type= scheme.scheme_type,
                scheme_category= scheme.scheme_category,
                sub_scheme_category= scheme.sub_scheme_category,
                scheme_code= scheme.scheme_code,
                nav_date= datetime.strptime(scheme.nav_date,"%d-%M-%Y"),
                nav_inr= float(scheme.nav_inr),
                isin= scheme.isin,
                pan= scheme.pan,
                closing_units= float(scheme.closing_units),
                total_cost_value_inr= float(scheme.total_cost_value_inr),
                        )



def extract(
    pdf_path: Path,
    out_dir: Path,
    *,
    mode: str = "auto",
    ocr_dpi: int = 300,
    save_text: Path | None = None,
) -> ParseResult:
    text, source = extract_text(pdf_path, mode=mode, ocr_dpi=ocr_dpi)
    if save_text is not None:
        save_text.parent.mkdir(parents=True, exist_ok=True)
        save_text.write_text(text, encoding="utf-8")
    print(f"Text source: {source}", file=sys.stderr)

    user = parse_personal(text)
    schemes, transactions = parse_schemes_and_txns(text, user)
    schemes = update_nav_details(schemes)
    # new_date_time = datetime.strptime("03-11-2026","%d-%M-%Y" )
    save_all_in_db(user, schemes, transactions)

    write_csv(
        out_dir / "users.csv",
        [asdict(user)],
        [
            "user_id",
            "name",
            "email",
            "phone_res",
            "mobile",
            "pan",
            "address",
            "statement_from",
            "statement_to",
        ],
    )
    write_csv(
        out_dir / "schemes.csv",
        [asdict(s) for s in schemes],
        [
            "scheme_id",
            "user_id",
            "amc_name",
            "folio_no",
            "holder_name",
            "scheme_name",
            "scheme_type",
            "scheme_category",
            "sub_scheme_category",
            "scheme_code",
            "nav_date",
            "nav_inr",
            "isin",
            "pan",
            "closing_units",
            "total_cost_value_inr",
        ],
    )
    write_csv(
        out_dir / "transactions.csv",
        [asdict(t) for t in transactions],
        [
            "transaction_id",
            "scheme_id",
            "date",
            "description",
            "amount_inr",
            "units",
            "price_inr",
            "unit_balance",
        ],
    )
    return ParseResult(user=user, schemes=schemes, transactions=transactions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pdf",
        nargs="?",
        default="/home/ammar/Documents/mfcentral/Alan_Romal.pdf",
        type=Path,
        help="Path to CAMS CAS PDF",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for CSVs (default: <pdf-stem>_csv next to PDF)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "text", "ocr"),
        default="auto",
        help="auto: text if selectable, else OCR; text/ocr force one path",
    )
    parser.add_argument("--ocr-dpi", type=int, default=300, help="OCR render DPI")
    parser.add_argument(
        "--save-text",
        type=Path,
        default=None,
        help="Also write extracted plain text (useful to inspect OCR)",
    )
    args = parser.parse_args()
    pdf_path: Path = args.pdf.expanduser().resolve()
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir or pdf_path.with_name(f"{pdf_path.stem}_csv")
    out_dir = out_dir.expanduser().resolve()

    result = extract(
        pdf_path,
        out_dir,
        mode=args.mode,
        ocr_dpi=args.ocr_dpi,
        save_text=args.save_text,
    )
    print(f"Wrote {out_dir}/users.csv          ({1} user)")
    print(f"Wrote {out_dir}/schemes.csv        ({len(result.schemes)} schemes)")
    print(f"Wrote {out_dir}/transactions.csv   ({len(result.transactions)} transactions)")
    print("Links: users.user_id <- schemes.user_id <- transactions.scheme_id")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
