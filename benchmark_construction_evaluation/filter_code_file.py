import json
import ast
import gzip
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re
import argparse


def make_soup(url, headers=None):
    try:
        response = requests.get(url, headers=headers)
    except Exception as e:
        print(e, flush=True)
        return None
    # return response
    if response.status_code == 200:
        return BeautifulSoup(response.text, 'html.parser')
    return None

def classify_code_ast(code):
    classified_code = {
        'imports': [],
        'functions': {},
        'classes': {},
        'class_methods': {},
        'others': ''
    }
    try:
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, ast.Import):
                classified_code['imports'].append(ast.unparse(node))
            elif isinstance(node, ast.ImportFrom):
                classified_code['imports'].append(ast.unparse(node))
            elif isinstance(node, ast.ClassDef):
                class_name = node.name
                classified_code['classes'][class_name] = ast.unparse(node)
                # iterate the function definition inside the class body
                for inside_class_node in node.body:
                    if isinstance(inside_class_node, ast.FunctionDef):
                        class_function_name = inside_class_node.name
                        classified_code['class_methods']['%s.%s' % (class_name, class_function_name)] = ast.unparse(
                            inside_class_node)
                    elif isinstance(inside_class_node, ast.AsyncFunctionDef):
                        class_function_name = inside_class_node.name
                        classified_code['class_methods']['%s.async_%s' % (class_name, class_function_name)] = ast.unparse(
                            inside_class_node)

            elif isinstance(node, ast.FunctionDef):
                function_name = node.name
                classified_code['functions'][function_name] = ast.unparse(node)
            elif isinstance(node, ast.AsyncFunctionDef):
                function_name = node.name
                classified_code['functions'][function_name] = ast.unparse(node)
            else:
                classified_code['others'] += ast.unparse(node) + '\n'
        return classified_code
    except:
        return classified_code

def get_library_alains(import_libs, target_library):
    library_name_list = []
    special_name_list = []

    import_lib_dic = {}
    for import_lib in import_libs:
        import_lib_dic[import_lib[1]] = import_lib[0]
        if '.' in import_lib[0]:
            special_name_list.append(import_lib)
            if target_library in import_lib[0]:
                library_name_list.append(import_lib)
        if import_lib[0].lower() == target_library:
            library_name_list.append(import_lib)
            # if import_lib[0] != import_lib[1]:
            #     library_name_list.append(import_lib)
    return library_name_list, special_name_list, import_lib_dic

def extract_imports(code):
    imports = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, alias.asname or alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                for alias in node.names:
                    imports.append((f"{module}.{alias.name}", alias.asname or alias.name))
    except:
        pass
    return imports

def star_filter(repo_html_url):
    soup = make_soup(repo_html_url)
    if soup:
        if soup.find(id='repo-stars-counter-star'):
            star_count_str = soup.find(id='repo-stars-counter-star').text
        else:
            return False
        if star_count_str.endswith('k'):
            star_count = int(float(star_count_str[:-1]) * 1000)
        else:
            star_count = int(soup.find(id='repo-stars-counter-star').text)
        if star_count >= 10:
            return True
    return False

def date_filter(code_html_url, year=2023, month=12, day=1):
    # return True if is after cutoff_time, else return False
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'github-verified-fetch': 'true',
    }
    try:
        date_str = requests.get(code_html_url.replace('blob', 'latest-commit'), headers=headers).json()['date']
    except:
        return False
    if date_str.endswith('Z'):
        date_str = date_str.replace("Z", "+00:00")
    # print(code_html_url)
    # print(date_str)
    given_time = datetime.fromisoformat(date_str)
    cutoff_time = datetime(year, month, day, tzinfo=timezone.utc)
    return given_time > cutoff_time

def API_call_filter(code, target_library='numpy', API_call_threshold=5):
    # split the code
    return_code_list = []
    classified_code = classify_code_ast(code)
    # get the alains of import library
    import_libs = []

    for import_line in classified_code['imports']:
        import_libs += extract_imports(import_line.strip())
    library_name_list, special_name_list, import_lib_dic = get_library_alains(import_libs, target_library)
    pattern = r'[().\[\]\s]+'
    target_library_name_list = []
    for item in library_name_list:
        target_library_name_list.append(item[0])
        target_library_name_list.append(item[1])

    print(target_library_name_list, flush=True)
    for key in classified_code['functions']:
        tmp_count = 0
        # function_code = remove_docstrings_and_comments(classified_code['functions'][key])
        function_code = classified_code['functions'][key]
        split_result = re.split(pattern, function_code)
        split_result = [s for s in split_result if s]
        for x in split_result:
            if x in target_library_name_list:
                tmp_count += 1
        if tmp_count >= API_call_threshold:
            return_code_list.append([function_code, 'function'])

    for key in classified_code['class_methods']:
        tmp_count = 0
        # function_code = remove_docstrings_and_comments(classified_code['class_methods'][key])
        function_code = classified_code['class_methods'][key]
        split_result = re.split(pattern, function_code)
        split_result = [s for s in split_result if s]
        for x in split_result:
            if x in target_library_name_list:
                tmp_count += 1
        if tmp_count >= API_call_threshold:
            return_code_list.append([function_code, 'class_method'])

    # other code
    # tmp_count = 0
    # other_code = remove_docstrings_and_comments(classified_code['others'])
    # split_result = re.split(pattern, other_code)
    # split_result = [s for s in split_result if s]
    # for x in split_result:
    #     if x in target_library_name_list:
    #         tmp_count += 1
    # if tmp_count >= API_call_threshold:
    #     return_code_list.append(other_code)

    return return_code_list

    # return import_libs, target_library_name_list, special_name_list, import_lib_dic


def rename_files():
    library = 'lightgbm'
    target_folder = 'intermediate_search_result/stackoverflow_search/github_search_result_initial/'
    file_list = sorted(os.listdir(target_folder + '%s/' % (library)), key=lambda x: int(x.split('.')[0]))

    save_folder = target_folder + 'test/'
    count = 0
    for file in file_list:
        with open(target_folder + '%s/' % (library) + file, 'r') as f:
            res = f.read()
        with open(save_folder + '%s_%s.json' % (library, count), 'w') as f:
            f.write(res)
        count += 1

# not used
def filtering():
    ds1000 = [json.loads(l) for l in gzip.open("dataset/ds1000_new.jsonl.gz", "rt").readlines()]

    res_list = []
    for i in range(1000):
    # for root, dirs, files in os.walk():
    #     for file_name in files:
        file_path = os.path.join('github_search_result_initial', '%s.json' % i)

        with open(file_path, 'r') as f:
            res = json.load(f)
        res_list.append(res)


    filtered_res_list = []

    for res in res_list:
        print(res['pid'], flush=True)
        save_file_path = 'github_search_result_filtered/%s.json' % res['pid']
        if os.path.exists(save_file_path):
            continue
        new_res = {}
        filtered_similar_code = []
        # each line of code
        for similar_code in res['similar_code_list']:
            # each searched similar code
            for i in range(len(similar_code['code_list'])):
                search_detail = similar_code['search_res']['items'][i]
                repo_url = search_detail['repository']['html_url']
                code_url = search_detail['html_url']
                code = similar_code['code_list'][i]

                # repo star filter
                if not star_filter(repo_url):
                    continue

                # code date filter
                if not date_filter(code_url):
                    continue

                # API filter
                if  ds1000[res['pid']]['metadata']['library'].lower() == 'pytorch':
                    filter_res = API_call_filter(code, 'torch')
                else:
                    filter_res = API_call_filter(code, ds1000[res['pid']]['metadata']['library'].lower())
                similar_code_tmp_dic = {
                    'code_snippet_list': filter_res,
                    'code': code,
                    'code_url': code_url,
                    'repo_url': repo_url,
                    'search_detail': search_detail
                }
                # if filter_res:
                if filter_res:

                    filtered_similar_code.append(similar_code_tmp_dic)
                print(code_url, flush=True)

        # if filtered_similar_code:
        new_res['pid'] = res['pid']
        new_res['reference_code'] = res['reference_code']
        new_res['code_line_list'] = res['code_line_list']
        new_res['similar_code_list'] = res['similar_code_list']
        new_res['filtered_similar_code'] = filtered_similar_code

        # with open(save_file_path, 'w') as f:
        #     f.write(json.dumps(new_res))


def filtering_wo_date_filtering(library, ds1000_or_stackoverflow='ds1000'):

    if ds1000_or_stackoverflow == 'ds1000':
        ds1000 = [json.loads(l) for l in gzip.open("ds1000.jsonl.gz", "rt").readlines()]

        base_folder = 'intermediate_search_result/DS1000_search/'
        initial_folder = base_folder + 'github_search_result_initial/'
        if not os.path.exists(base_folder + 'github_search_result_filtered/'):
            os.mkdir(base_folder + 'github_search_result_filtered/')

        file_list = sorted(os.listdir(initial_folder), key=lambda x: int(x.split('.')[0]))
        for file_name in file_list:
            file_path = os.path.join(initial_folder + file_name)
            with open(file_path, 'r') as f:
                res = json.load(f)

            print(res['pid'], flush=True)
            save_file_path = base_folder + 'github_search_result_filtered/%s.json' % res['pid']
            if os.path.exists(save_file_path):
                continue
            new_res = {}
            filtered_similar_code = []
            # each line of code
            for similar_code in res['similar_code_list']:
                # each searched similar code
                for i in range(len(similar_code['code_list'])):
                    search_detail = similar_code['search_res']['items'][i]
                    repo_url = search_detail['repository']['html_url']
                    code_url = search_detail['html_url']
                    code = similar_code['code_list'][i]

                    # repo star filter
                    if not star_filter(repo_url):
                        continue

                    # # code date filter
                    # if not date_filter(code_url):
                    #     continue

                    # API filter
                    if ds1000[res['pid']]['metadata']['library'].lower() == 'pytorch':
                        filter_res = API_call_filter(code, 'torch')
                    else:
                        filter_res = API_call_filter(code, ds1000[res['pid']]['metadata']['library'].lower())

                    similar_code_tmp_dic = {
                        'code_snippet_list': filter_res,
                        'code': code,
                        'code_url': code_url,
                        'repo_url': repo_url,
                        'search_detail': search_detail
                    }
                    if filter_res:
                        filtered_similar_code.append(similar_code_tmp_dic)
                    print(code_url, flush=True)

            new_res['pid'] = res['pid']
            new_res['reference_code'] = res['reference_code']
            new_res['code_line_list'] = res['code_line_list']
            new_res['similar_code_list'] = res['similar_code_list']
            new_res['filtered_similar_code'] = filtered_similar_code

            with open(save_file_path, 'w') as f:
                f.write(json.dumps(new_res))
    else:
        base_folder = 'intermediate_search_result/stackoverflow_search/'
        initial_folder = base_folder + 'github_search_result_initial/'

        if not os.path.exists(base_folder + 'github_search_result_filtered/'):
            os.mkdir(base_folder + 'github_search_result_filtered/')

        file_list = sorted(os.listdir(initial_folder),
                           key=lambda x: [x.rstrip('.json').split('_')[0], int(x.rstrip('.json').split('_')[1])])
        for file_name in file_list:
            if library not in file_name:
                continue
            file_path = os.path.join(initial_folder + file_name)
            try:
                with open(file_path, 'r') as f:
                    res = json.load(f)
                    # res['pid'] = 'stackoverflow_' + file_name.replace('.json', '')
                    res['pid'] = file_name.replace('.json', '')
            except:
                continue
            print(res['pid'], flush=True)
            save_file_path = base_folder + 'github_search_result_filtered/%s.json' % res['pid']
            if os.path.exists(save_file_path):
                continue
            new_res = {}
            filtered_similar_code = []
            # each line of code
            for similar_code in res['similar_code_list']:
                # each searched similar code
                for i in range(len(similar_code['code_list'])):
                    search_detail = similar_code['search_res']['items'][i]
                    repo_url = search_detail['repository']['html_url']
                    code_url = search_detail['html_url']
                    code = similar_code['code_list'][i]

                    # repo star filter
                    if not star_filter(repo_url):
                        continue

                    # # code date filter
                    # if not date_filter(code_url):
                    #     continue

                    # API filter
                    if 'pytorch' in res['pid']:
                        filter_res = API_call_filter(code, 'torch')
                    else:
                        filter_res = API_call_filter(code, res['pid'].split('_')[0]) # library name

                    similar_code_tmp_dic = {
                        'code_snippet_list': filter_res,
                        'code': code,
                        'code_url': code_url,
                        'repo_url': repo_url,
                        'search_detail': search_detail
                    }
                    if filter_res:
                        filtered_similar_code.append(similar_code_tmp_dic)
                    print(code_url, flush=True)

            new_res['pid'] = res['pid']
            new_res['reference_code'] = res['reference_code']
            new_res['code_line_list'] = res['code_line_list']
            new_res['similar_code_list'] = res['similar_code_list']
            new_res['filtered_similar_code'] = filtered_similar_code

            with open(save_file_path, 'w') as f:
                f.write(json.dumps(new_res))


if __name__ == '__main__':
    # filtering_wo_date_filtering('scipy', ds1000_or_stackoverflow='stackoverflow')
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--library",
        type=str,
        choices=['numpy', 'pandas', 'matplotlib', 'scipy', 'sklearn',
                 'tensorflow', 'pytorch', 'seaborn', 'keras', 'lightgbm', 'all'],
        help="Choose library",
        required=True,
    )
    parser.add_argument(
        "-s",
        "--source",
        type=str,
        choices=['ds1000', 'stackoverflow'],
        help="Choose library",
        required=True,
    )
    args = parser.parse_args()
    filtering_wo_date_filtering(args.library, ds1000_or_stackoverflow=args.source)