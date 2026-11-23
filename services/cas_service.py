"""Extract investors, holdings and transactions from a CAMS/KFintech CAS PDF."""
import io
import re
from datetime import date, datetime
from decimal import Decimal
import requests
import casparser
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.queries.cas import (
    add_new_transactions,
    get_or_create_user,
    mark_failed,
    mark_processed,
    mark_processing,
    upsert_holding,
)
from app.db.schema import Document
from app.services.s3_service import download_pdf

_DATE_FORMATS = ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def _to_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _to_date(value: date | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _to_phone(value: str | None) -> int | None:
    digits = re.sub(r"\D", "", value or "")
    return int(digits[-10:]) if digits else None


def _enum_value(value) -> str | None:
    return None if value is None else str(getattr(value, "value", value))


def _parse_pdf(pdf_bytes: bytes, password: str | None):
    return casparser.read_cas_pdf(io.BytesIO(pdf_bytes), password or "")


def _scheme_values(folio, scheme) -> dict:
    valuation = scheme.valuation
    close = scheme.close
    cost = valuation.cost
    unit_cost = (cost / close) if (cost is not None and close) else None

    # Getting nav 
    nav_latest = get_nav_latest(scheme.amfi)
    scheme_category = None
    sub_scheme_category = None
    nav_date = _to_date(valuation.date)
    nav = valuation.nav
    last_updated_nav = datetime.now()
    if nav_latest:
        split_schema = nav_latest['meta']['scheme_category'].split('-')
        scheme_category = split_schema[0].strip()
        if scheme_category == "Fund of Funds Scheme (Domestic)":
            scheme_category = 'Other Scheme'
        scheme_category = scheme_category
        sub_scheme_category = split_schema[1].strip()

        ## get nav data
        nav_date = _to_date(nav_latest['data'][0]['date'])
        nav = nav_latest['data'][0]['nav']
        last_updated_nav = datetime.now()
        


    return {
        "amc_name": folio.amc,
        "scheme_name": scheme.scheme,
        "scheme_type": scheme.type,
        "scheme_code": scheme.amfi,
        "nav_date": _to_date(valuation.date),
        "last_updated_nav": datetime.now(),
        "nav_inr": _to_float(valuation.nav),
        "closing_units": _to_float(close),
        "closing_unit_cost": _to_float(unit_cost),
        "opening_units": _to_float(scheme.open),
        "total_cost": _to_float(cost),
        "market_value": _to_float(valuation.value),
        "rta": scheme.rta,
        "rta_code": scheme.rta_code,
        "advisor": scheme.advisor,
        "scheme_category" : scheme_category,
        "sub_scheme_category":sub_scheme_category,
        'nav_inr': _to_float(nav),
        'nav_date': nav_date,
        'last_updated_nav' : last_updated_nav
    }


def _txn_rows(scheme) -> list[dict]:
    return [
        {
            "date": _to_date(t.date),
            "description": t.description,
            "amount_inr": _to_float(t.amount),
            "units": _to_float(t.units),
            "nav": _to_float(t.nav),
            "balance": _to_float(t.balance),
            "type": _enum_value(t.type),
            "divident_rate": _to_float(t.dividend_rate),
            "gift_folio": t.gift_folio,
        }
        for t in scheme.transactions
    ]


async def process_document(db: AsyncSession, document: Document) -> None:
    """Parse the stored PDF and save users (one per PAN), holdings, transactions.

    Never raises for bad/unsupported PDFs: the document is marked `failed`
    with a message instead, so the upload itself is never lost.
    """
    mark_processing(document)
    await db.commit()

    try:
        pdf_bytes = await run_in_threadpool(download_pdf, document.s3_key)
        data = await run_in_threadpool(_parse_pdf, pdf_bytes, document.password)
    except Exception as exc:  # wrong password, not a CAS, S3 error, ...
        mark_failed(document, f"Could not read statement: {exc}")
        await db.commit()
        return

    try:
        info = data.investor_info
        period = data.statement_period
        start, end = _to_date(period.from_), _to_date(period.to)

        # group folios by PAN -> one user each
        by_pan: dict[str | None, list] = {}
        for folio in data.folios:
            by_pan.setdefault(folio.PAN, []).append(folio)
  

        for pan, folios in by_pan.items():
            profile = {
                "name": folios[0].name or info.name,
                "email": info.email,
                "phone_no": _to_phone(info.mobile),
                "address": info.address,
                "statement_from": start,
                "statement_to": end,
                "reference": document.id,  # link user -> source document
            }
            user = await get_or_create_user(db, document.credential_id, pan, profile)

            for folio in folios:
                for scheme in folio.schemes:
                    holding = await upsert_holding(
                        db,
                        user.id,
                        folio.folio,
                        scheme.isin,
                        scheme.scheme,
                        _scheme_values(folio, scheme),
                    )
                    await add_new_transactions(db, holding.id, _txn_rows(scheme))

        mark_processed(document, start, end)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        mark_failed(document, f"Could not save statement: {exc}")
        await db.commit()


def get_nav_latest(scheme_code : str) -> list[dict]:

    url = f"https://api.mfapi.in/mf/{scheme_code}/latest"
    headers = {"accept": "application/json"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()