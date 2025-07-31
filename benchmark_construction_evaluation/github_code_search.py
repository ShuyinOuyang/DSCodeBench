import argparse
import gzip
import json
import os.path
import time
import urllib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone


def get_search_result(url, headers=None):
    # request url and get the response

    response = requests.get(url, headers=headers)
    # return response
    if response.status_code == 200:
        return json.loads(response.text), ''
        # return BeautifulSoup(response.text, 'html.parser')
    else:
        print('get_search_result error')
        print(response.text)
    if 'API rate limit' in response.text:
        return None, 'rate limit'
    else:
        return None, ''

def get_code(url, headers=None):
    # get code(text) from response
    response = requests.get(url, headers=headers)
    # return response
    if response.status_code == 200:
        return response.text, ''
    else:
        print('get_code error')
        print(response.text)
        # return BeautifulSoup(response.text, 'html.parser')
    if 'API rate limit' in response.text:
        return None, 'rate limit'
    else:
        return None, ''

def make_soup(url, headers=None):
    # get text from response and make it into soup object

    response = requests.get(url, headers=headers)
    # return response
    if response.status_code == 200:
        return BeautifulSoup(response.text, 'html.parser')
    return None

# use reference code as query to search in the github
def split_reference_code(code):
    final_list = []
    code_line_list = code.split('\n')
    for code_line in code_line_list:
        if code_line.startswith('def'):
            continue
        elif 'return' in code_line:
            continue
        elif 'import' in code_line:
            continue
        elif len(code_line.strip()) < 10:
            continue
        else:
            if code_line.strip():
                final_list.append(code_line.strip())
    return final_list

def count_lines_in_file(file_path):
    with open(file_path, 'r') as file:
        total_lines = sum(1 for _ in file)
    return total_lines

def star_filter(repo_html_url, star_threshold=10):
    # the repo need to have at least 10 stars
    soup = make_soup(repo_html_url)
    star_count = int(soup.find(id='repo-stars-counter-star').text)
    if star_count >= star_threshold:
        return True
    else:
        return False

def date_filter(code_html_url, year=2023, month=12, day=1):
    # return True if is after cutoff_time, else return False

    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'github-verified-fetch': 'true',
    }

    date_str = requests.get(code_html_url.replace('blob', 'lastest-commit'), headers=headers).json()['date']
    given_time = datetime.fromisoformat(date_str)
    cutoff_time = datetime(year, month, day, tzinfo=timezone.utc)
    return given_time > cutoff_time

def request_github_api_detail(headers=None):
    response = requests.get('https://api.github.com/rate_limit', headers=headers)
    if response.status_code == 200:
        return json.loads(response.text)
    else:
        return None

def check_rate_limit(headers=None):
    rate_limit = request_github_api_detail(headers)
    if rate_limit:
        if rate_limit['resources']['code_search']['remaining'] == 0:
            time.sleep(10)

def crawl_data_from_github_based_on_ds1000():
    # load ds1000 dataset
    ds1000 = [json.loads(l) for l in gzip.open("ds1000.jsonl.gz", "rt").readlines()]

    github_api_base_url = 'https://api.github.com/search/code?'

    with open('personal_token/github_token.json', 'r') as f:
        headers = json.load(f)

    saved_file_dir = 'github_search_result_initial/'
    rate_limit_flag = False

    for problem in ds1000:
        pid = ds1000.index(problem)
        save_file_path = saved_file_dir + '%s.json'% (pid)
        # judge whether the file exist
        if os.path.exists(save_file_path):
            continue
        # else:
        #     with open(save_file_path, 'w') as f:
        #         f.write('')

        print(pid)
        search_res_dic = {}
        code_line_list = split_reference_code(problem['reference_code'])

        search_res_dic['reference_code'] = problem['reference_code']
        search_res_dic['code_line_list'] = code_line_list
        search_res_dic['pid'] = pid

        similar_code_list = []

        for code_line in code_line_list:
            time.sleep(2)
            # url_suffix = urllib.parse.urlencode(query_dic)
            url = github_api_base_url + 'q=%s+in:file+language:python' % (urllib.parse.quote(code_line))
            print(url)
            try:
                search_res, err_info = get_search_result(url, headers)

                check_rate_limit(headers)
                code_list = []
                for item in search_res['items']:
                    code_res, err_info = get_search_result(item['url'], headers)

                    check_rate_limit(headers)
                    code, err_info = get_code(code_res['download_url'], headers)

                    check_rate_limit(headers)
                    code_list.append(code)
                similar_code_list.append({
                    'url': url,
                    'search_res': search_res,
                    'code_list': code_list
                })
            except Exception as e:
                print(e)
                print('Get search result fails.')
                continue
        search_res_dic['similar_code_list'] = similar_code_list
        with open(save_file_path, 'w') as f:
            f.write(json.dumps(search_res_dic))

def crawl_data_from_github_based_on_stackoverflow(library='seaborn', user_id=0):
    github_api_base_url = 'https://api.github.com/search/code?'

    with open('personal_token/github_token_%s.json' % user_id, 'r') as f:
        headers = json.load(f)

    saved_file_dir = 'intermediate_search_result/stackoverflow_search/github_search_result_initial/'

    if not os.path.exists(saved_file_dir + '%s/' % library):
        os.makedirs(saved_file_dir + '%s/' % library)

    with open('stackoverflow_new_data/%s.json' % (library), 'r') as f:
        res_list = json.load(f)

    similar_code_list = []
    for res in res_list:
        pid = res_list.index(res)

        save_file_path = saved_file_dir + '%s/%s.json'% (library, pid)

        if os.path.exists(save_file_path):
            continue
        print(save_file_path)
        try:
            answer_code = res['answers'][0]['answer_code_list'][0]
        except:
            continue
        search_res_dic = {}
        code_line_list = split_reference_code(answer_code)
        search_res_dic['reference_code'] = answer_code
        search_res_dic['code_line_list'] = code_line_list
        search_res_dic['pid'] = pid

        for code_line in code_line_list:
            # print(code_line)
            time.sleep(2)
            # url_suffix = urllib.parse.urlencode(query_dic)
            url = github_api_base_url + 'q=%s+in:file+language:python' % (urllib.parse.quote(code_line))
            print(url)
            try:
                search_res, err_info = get_search_result(url, headers)
                check_rate_limit(headers)
                code_list = []
                count = 0
                for item in search_res['items']:
                    code_res, err_info = get_search_result(item['url'], headers)

                    check_rate_limit(headers)
                    code, err_info = get_code(code_res['download_url'], headers)

                    check_rate_limit(headers)
                    code_list.append(code)

                    print('code', count)
                    count += 1
                similar_code_list.append({
                    'url': url,
                    'search_res': search_res,
                    'code_list': code_list
                })
            except Exception as e:
                print(e)
                print('Get search result fails.')
                continue
        search_res_dic['similar_code_list'] = similar_code_list
        with open(save_file_path, 'w') as f:
            f.write(json.dumps(search_res_dic))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--library", type=str, choices=['numpy', 'pandas', 'matplotlib', 'scipy', 'sklearn',
                 'tensorflow', 'pytorch', 'seaborn', 'keras', 'lightgbm'])
    parser.add_argument("-s", "--source", type=str,  choices=[''], required=True)
    args = parser.parse_args()

    if args.source == 'ds1000':
        crawl_data_from_github_based_on_ds1000()
    elif args.source == 'stackoverflow':
        if args.library == 'pytorch':
            crawl_data_from_github_based_on_stackoverflow('torch')
        else:
            crawl_data_from_github_based_on_stackoverflow(args.library)