import requests

q  = "360 ONE Focused Fund Direct Plan Growth"
q = "quant ELSS Tax Saver Fund - Direct Plan"
q = "Bandhan Small Cap Fund-Regular Plan-Growth"

#[{'schemeCode': 131580, 'schemeName': '360 ONE Focused Fund - Direct Plan - GROWTH Option'}]
#returns a list of dictionaries
def get_mf_search(q : str) -> list[dict]:

    url = "https://api.mfapi.in/mf/search"
    params = {"q": q}
    headers = {"accept": "application/json"}

    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()

    return response.json()

def get_nav_latest(scheme_code : str) -> list[dict]:

    url = f"https://api.mfapi.in/mf/{scheme_code}/latest"
    headers = {"accept": "application/json"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()

def update_mf_schema(nav_latest : dict) -> dict:
    split_schema = nav_latest['meta']['scheme_category'].split('-')
    scheme_category = split_schema[0].strip()
    if scheme_category == "Fund of Funds Scheme (Domestic)":
        scheme_category = 'Other Scheme'
    nav_latest['meta']['scheme_category'] = scheme_category
    nav_latest['meta']['sub_scheme_category'] = split_schema[1].strip()
    return nav_latest

def filter_mf_search_based_on_isin(scheme_name:str, isin : str) -> dict:

    mf_search = get_mf_search(scheme_name)
    for item in mf_search:
        nav_latest = get_nav_latest(item['schemeCode'])
        # print("the nav_latest is", nav_latest)
        print()
        if nav_latest['meta']['isin_growth'] == isin:
            nav_latest = update_mf_schema(nav_latest)
            return nav_latest




if __name__ == "__main__":
    q = "Groww Silver ETF FOF"
    datas = get_mf_search(q)
    print(datas)


    fil = filter_mf_search_based_on_isin(q, "INF966L01986")

    print(fil, 'the latest is')
