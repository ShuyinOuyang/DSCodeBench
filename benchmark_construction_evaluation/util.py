import json
import gzip
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re
import ast
import asyncio
import numpy as np
import builtins

import asyncgpt

def make_soup(url, headers=None):
    response = requests.get(url, headers=headers)
    # return response
    if response.status_code == 200:
        return BeautifulSoup(response.text, 'html.parser')
    return None

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

    print(target_library_name_list)
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
        # print(split_result)
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


def remove_docstrings_and_comments(code):
    # Remove multi-line docstrings (both ''' and """)
    code_no_docstrings = re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', '', code)

    # Remove single-line comments
    # code_no_comments = re.sub(r'#.*', '', code_no_docstrings)
    code_no_comments = re.sub(r'(^|\s)#.*', '', code_no_docstrings)

    # Remove empty lines left after removal
    code_cleaned = "\n".join([line for line in code_no_comments.splitlines() if line.strip() != ""])

    return code_cleaned

def get_docstrings_and_comments(code):
    # file = 'filter_code_demo_2.py'
    # with open(file, 'r') as f:
    #     code = f.read()

    a_ast = ast.parse(code)
    docstrings = []
    for node in ast.walk(a_ast):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            docstring = ast.get_docstring(node)
            if isinstance(node, ast.FunctionDef):
                if hasattr(node, 'name'):
                    docstrings.append((node.name, 'astFunctionDef', docstring))
            elif isinstance(node, ast.AsyncFunctionDef):
                if hasattr(node, 'name'):
                    docstrings.append((node.name, 'astAsyncFunctionDef', docstring))
            elif isinstance(node, ast.ClassDef):
                if hasattr(node, 'name'):
                    docstrings.append((node.name, 'astClassDef', docstring))
            else:
                docstrings.append(('Module', 'asModule', docstring))


    comments = re.findall(r'#.*', code)

    return docstrings, comments

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

def classify_code(code):
    # Regular expressions for different parts of the code
    import_pattern = r'^(import\s+\w+|from\s+\w+(\.\w+)*\s+import\s+[\w, ]+)'
    function_pattern = r'^def\s+\w+\s*\(.*?\)\s*(->\s*[^:]+)?\s*:'
    # function_pattern = r'^def\s+\w+\s*\(.*\):'

    # Initialize dictionary to store classified code
    classified_code = {
        'imports': [],
        'functions': {},
        'others': ''
    }

    lines = code.splitlines()

    current_function = None
    current_function_code = []
    inside_function = False
    inside_docstring = False
    function_indent_level = 0
    current_indent_level = 0
    for line in lines:
        if line.lstrip() != '':
            current_indent_level = len(line) - len(line.lstrip())
            if current_indent_level == 0:
                inside_function = False

        if re.match(import_pattern, line.strip()):
            classified_code['imports'].append(line)

        elif (re.match(function_pattern, line)) and (not inside_function):
        # elif re.match(function_pattern, line):
              # or (function_indent_level == len(line) and line.strip() == '')):
            if current_function:
                classified_code['functions'][current_function] = '\n'.join(current_function_code).strip()
                current_function_code = []

            # Extract the function name
            current_function = re.search(r'def\s+(\w+)', line).group(1)
            current_function_code.append(line)
            function_indent_level = len(line) - len(line.lstrip())
            inside_function = True  # Now inside a function
        elif inside_function:
            # if line.lstrip() != '':
            #     current_indent_level = len(line) - len(line.lstrip())
            # else:
            #     pass
            if current_indent_level > function_indent_level or inside_docstring:
                current_function_code.append(line)

                # Check if we're entering or leaving a docstring
                if '"""' in line or "'''" in line:
                    inside_docstring = not inside_docstring
            else:
                # End of the current function
                classified_code['functions'][current_function] = '\n'.join(current_function_code).strip()
                current_function = None
                current_function_code = []
                inside_function = False
                function_indent_level = 0
                classified_code['others'] += line + '\n'
        else:
            # If not inside a function, it's part of 'others'
            # if line.lstrip() != '':
            classified_code['others'] += line + '\n'

    # Add the last function if any
    if current_function:
        classified_code['functions'][current_function] = '\n'.join(current_function_code).strip()

    # Remove any leading/trailing whitespace from 'others'
    classified_code['others'] = classified_code['others'].strip()

    return classified_code

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


def get_library_from_code(code):
    classified_code = classify_code_ast(code)
    import_libs = []
    for import_line in classified_code['imports']:
        import_libs += extract_imports(import_line.strip())
    return import_libs


async def get_response_conversation(index, pid, message, bot, ds1000, setting={}):
    if 'temperature' in setting:
        temperature = setting['temperature']
    else:
        temperature = 0

    try:
        completion = await bot.chat_complete(message, model=setting['model'], temperature=temperature)
        print(completion)
    except Exception as e:
        print(e)

        res = {'index': index,
               'pid': pid,
               'model': setting['model'],
               # 'metadata': ds1000[index]['metadata'],
               'temperature': temperature,
               'prompt': message[-1]['content'],
               'completion': {},
               'message': message,
               'response': ''
               }
        return res


    if "choices" in completion:
        res = {'index': index,
               'pid': pid,
               'model': setting['model'],
               # 'metadata': ds1000[index]['metadata'],
               'temperature': temperature,
               'prompt': message[-1]['content'],
               'completion': completion,
               'message': message,
               'response': completion['choices'][0]['message']['content']
               }
    else:
        res = {'index': index,
               'pid': pid,
               'model': setting['model'],
               # 'metadata': ds1000[index]['metadata'],
               'temperature': temperature,
               'prompt': message[-1]['content'],
               'completion': completion,
               'message': message,
               'response': ''
               }
    return res


async def openai_model_conversation(index_pid_message_list, setting):
    # code repair
    if 'deepseek' in setting['model']:
        with open('personal_token/deepseek_info.json', 'r') as f:
            info_dic = json.load(f)
    elif 'codestral' in setting['model']:
        with open('personal_token/codestral_info.json', 'r') as f:
            info_dic = json.load(f)
    else:
        with open('personal_token/gpt_info.json', 'r') as f:
            info_dic = json.load(f)
    ds1000 = [json.loads(l) for l in gzip.open("dataset/ds1000_new.jsonl.gz", "rt").readlines()]

    bot = asyncgpt.AsyncGPT(api_key=info_dic['api_key'], organization=info_dic['organization'], model=setting['model'])
    prompt_list = [get_response_conversation(id, pid, message, bot, ds1000, setting)
                   for id, pid, message in index_pid_message_list]
    res_list = await asyncio.gather(*prompt_list)
    return res_list

def extract_code(text):
    # This regex will match any text within triple backticks
    pattern = r'```(?:[\w]+)?\n(.*?)```'
    # Find all matches and join them if there are multiple code blocks
    code_blocks = re.findall(pattern, text, re.DOTALL)
    if code_blocks:
        return code_blocks[0]
    else:
        return ''

def extract_codeproblem(response):
    pattern = r"Code problem description:\n(.*)"
    # Using re.search to find matches
    match = re.search(pattern, response, re.DOTALL)
    if match:
        code_problem = match.group(1).strip()
        return code_problem
    else:
        return response

def extract_small_test_case(response):
    pattern = r"Example Input & Output:\n(.*)"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        code_problem = match.group(1).strip()
        return code_problem
    else:
        return response

def get_function_names(code):
    # Parse the code string into an AST
    tree = ast.parse(code)

    # Traverse the nodes in the AST to find function definitions
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef)]

    # func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    # print(len(functions))
    # Return the last function name if any are found
    # function_name = functions[-1].name if functions else None
    # function_parameter_count = len(functions[-1].args.args)
    function_name_list = [function.name for function in functions]
    return function_name_list

def get_main_function_name_and_parameter_count(code):
    # Parse the code string into an AST
    try:
        tree = ast.parse(code)
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef)]
        function_name = functions[-1].name if functions else None
        function_parameter_count = len(functions[-1].args.args)
        return function_name, function_parameter_count
    except:
        return None, None

def prepare_exec_code(ground_truth_code, test_case_script, get_input_output):
    exec_code = ''
    main_function_name, main_function_parameter_count = get_main_function_name_and_parameter_count(ground_truth_code)
    if get_input_output:
        if main_function_name:
            if main_function_parameter_count > 1:
                exec_code = f'''
import random
random.seed(42)
{ground_truth_code}

{test_case_script}
test_case_input_list = test_case_input_generator(10)
test_case_output_list = []
for test in test_case_input_list:
    try:
        output = {main_function_name}(*test)
        test_case_output_list.append(1)
    except:
        test_case_output_list.append(0)
'''
            else:
                exec_code = f'''
import random
random.seed(42)
{ground_truth_code}

{test_case_script}
test_case_input_list = test_case_input_generator(10)
test_case_output_list = []
for test in test_case_input_list:
    try:
        output = {main_function_name}(test)
        test_case_output_list.append(1)
    except:
        test_case_output_list.append(0)
'''
    else:
        if main_function_name:
            if main_function_parameter_count > 1:
                exec_code = f'''
import random
random.seed(42)
{ground_truth_code}

{test_case_script}
test_case_input_list = test_case_input_generator(10)
for test in test_case_input_list:
    {main_function_name}(*test)
'''
            else:
                exec_code = f'''
import random
random.seed(42)
{ground_truth_code}

{test_case_script}
test_case_input_list = test_case_input_generator(10)
for test in test_case_input_list:
    {main_function_name}(test)
'''

    return exec_code
