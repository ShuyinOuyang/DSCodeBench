import argparse
import json
import os
import ast

from util import *
import tempfile
import resource
import subprocess
import signal

deepseek = False
if deepseek:
    setting_generate_code_problem = {
        'model': 'deepseek-chat',
        'temperature': 0,
    }

    setting_generate_test_cases = {
        'model': 'deepseek-chat',
        'temperature': 1,
    }

    setting_generate_code = {
        'model': 'deepseek-chat',
        'temperature': 1,
    }
else:
    setting_generate_code_problem = {
        # 'model': 'gpt-3.5-turbo-0125',  # gpt-3.5-turbo-0125
        'model': 'gpt-4o-mini',
        'temperature': 0,
    }

    setting_generate_test_cases = {
        # 'model': 'gpt-3.5-turbo-0125',  # gpt-3.5-turbo-0125
        'model': 'gpt-4o-mini',
        'temperature': 1,
    }

    setting_generate_code = {
        # 'model': 'gpt-3.5-turbo-0125',  # gpt-3.5-turbo-0125
        'model': 'gpt-4o-mini',
        'temperature': 1,
    }

def add_matplotlib_agg(code):
    lines = code.splitlines()
    result = []
    added_agg = False

    for line in lines:
        result.append(line)
        if 'matplotlib' in line and 'import' in line and (not added_agg):
            result.append("import matplotlib\nmatplotlib.use('Agg')")
            added_agg = True

    return '\n'.join(result)

def prompt_change_main_function(solution, else_context):
    prompt = ('please change the code based on the following rules:\n'
              '1. if the variable in the code is read from files, then discard the file reading code and put the variable as a function input parameter;\n'
              '2. discard all the file writing code;\n'
              '3. if the function has no return, please return the variable that the function has the most operations on;\n'
              '4. remove all the logging inside the code;\n'
              '5. check the redundancy of code, remove all the unnecessary code while ensuring the correctness of overall code;\n'
              '6. please return the refined version of both # Code Context # and # Main Code # together in a code block. And before the # Main Code # please add a comment line with \'# main code\'\n\n'
              '# Code Context #\n'
              '%s\n\n'
              '# Main Code #\n'
              '%s'
              % (else_context, solution))

    return prompt

def prompt_generate_codeproblem(ground_truth_code, test_case, valid_test_output_list):
    valid_test_output_natural_language = ('Among the test cases, only test case No. %s are available. '
                                          % (', '.join([str(i+1) for i in range(len(valid_test_output_list)) if valid_test_output_list[i] != 0])))
    prompt = ('Use the following information to generate a code problem description. '
                     'The code problem description should be described in detail, '
                     'including problem description, input & output format and examples, and constraints, '
                     'so that solution can be generated only depending on '
                     'code problem description. \n\n'
                     '# Code #\n'
                     '%s\n\n'
                     '# Test case #\n'
                     '%s\n\n'
                     '%s\n\n'
                     '# Response #\n'
                     'The return should follow the following format (replace {} into the code problem):\n\n'
                     'Code problem description:\n{}' % (ground_truth_code, test_case, valid_test_output_natural_language))

    return prompt

def prompt_generate_solution(code_problem_description):
    prompt = ('Please generate Python3 solution for the following code problem description:\n\n'
              '# Code problem description #\n'
              '%s\n\n'
              '# Response #\n'
              'The return should follow the following format (replace {} with the solution). '
              'And the solution function name should be \'solution\':\n\n'
              'Solution:\n{}' % (code_problem_description))

    return prompt

# generate LLM's prompt for sample test case input (10 for each ground truth code)
def prompt_generate_sample_test_case_input(solution, else_context, test_case_num=10):
    prompt = ('Generate %s high-quality test case input for the # Code # below. '
              'The # Code Context # provide the context of the # Code # function.'
              'The generated test cases input should be stored in a list named \'test_input\'. \n'
              '```python\n'
              'input1 = xxx\n'
              'input2 = xxx\n'
              'input3 = xxx\n'
              'test_input = [input1, input2, input3]\n'
              '```\n'
              # 'The input list contains input strings that can be directly put inside \n\n'
              '# Code #\n'
              '%s\n\n'
              '# Code Context #\n'
              '%s\n\n'
              '# Response #\n'
              'The return test case input should be put into Markdown code block\n\n'
              % (test_case_num, solution, else_context))


    return prompt

def prompt_generate_testcase_script_from_solution_and_codeproblem(ground_truth_code, code_problem, test_case_code, valid_test_output_list):
    valid_test_output_natural_language = ('Among the test cases, only test case No. %s are available. '
                                          % (', '.join([str(i+1) for i in range(len(valid_test_output_list)) if valid_test_output_list[i] != 0])))
    prompt = ('Please generate a python function named \'test_case_input_generator\' to generate high-quality test cases input for the following code problem. '
              'The script should take n (the total number of test cases input, set default as 200) as input. '
              'Do not use any example test case in the code. '
              'The generated test case input should cover the edge cases. '
              'The input should follow the restriction in the code problem and the ground truth solution.'
              '# Code Problem #\n'
              '%s\n\n'
              '# Ground Truth Solution #\n'
              '%s\n\n'
              '# Example Test Case #\n'
              '%s\n\n'
              '%s\n\n'
              '# Response #\n'
              'The return script should be put into Markdown code block\n\n'
              % (ground_truth_code, code_problem, test_case_code, valid_test_output_natural_language))


    return prompt

def prompt_update_testcase_script(ground_truth_code, test_case_script, error_info, test_case_input):
    final_error_info = ('When taking the following as input:\n%s\n'
                        'The ground truth function has the following error:\n'
                        '%s\n' % (test_case_input, error_info))

    prompt = ('Please re-generate a python function named \'test_case_input_generator\' to generate high-quality '
              'test cases input for the following ground truth solution. '
              'The previous version of the script has an error. '
              'The script should take n (the total number of test cases input, set default as 200) as input. '
              'Do not use any example test case in the code. '
              '# Ground Truth Solution #\n'
              '%s\n\n'
              '# Previous Test Case Generation Script #\n'
              '%s\n\n'
              '# Error Info #\n'
              '%s\n\n'
              '# Response #\n'
              'The return script should be put into Markdown code block\n\n'
              % (ground_truth_code, test_case_script, final_error_info))
    return prompt

def post_change_function():
    with open('intermediate_result/pandas_code_polish_0.json', 'r') as f:
        res_list = json.load(f)


    # Use GPT to refine the code
    # 1. change all file reading into function input
    # 2. remove all file writing
    # 3. remove logging
    # 4. make the main function has return if they

    for i in range(len(res_list)):
        res = res_list[i]
        ground_truth_code_file_path = res['pid']
        refined_code = extract_code(res['response'])[0]
        save_path = ground_truth_code_file_path.replace('ground_truth_code_filtered_deduplicated',
                                                        'ground_truth_code_filtered_deduplicated_polished')

        with tempfile.TemporaryDirectory() as tmp_dir:
            old_dir = os.getcwd()
            try:
                os.chdir(tmp_dir)
                exec(refined_code)
                os.chdir(old_dir)
                with open(save_path, 'w') as f:
                    f.write(refined_code)
            except:
                os.chdir(old_dir)
                with open(ground_truth_code_file_path, 'r') as f:
                    ground_truth_code = f.read()
                with open(save_path, 'w') as f:
                    f.write(ground_truth_code)

def generate_changed_main_function():
    target_dir_path = 'ground_truth_code_filtered_deduplicated/'
    file_name_list = sorted(os.listdir(target_dir_path), key=lambda name: tuple(map(int, name.rstrip(".py").split('_'))))
    index_x_message_list = []

    for idx in range(len(file_name_list)):
        file_name = file_name_list[idx]
        if int(file_name.split('_')[0]) > 290:
            break
        with open(target_dir_path + file_name, 'r') as f:
            code = f.read()

        # get the main function
        code_line_list = code.split('\n')
        main_function = ''
        else_context = ''
        main_function_flag = False
        for line in code_line_list:
            if main_function_flag:
                main_function += line + '\n'
            else:
                if line != '# main code':
                    else_context += line + '\n'
            if line == '# main code':
                main_function_flag = True
        # index_x_message_list.append([file_name, main_function, else_context])

        # # use gpt to generate test cases
        message = [
            {"role": "system", "content": 'You are a helpful programming assistant. '
                                          'You are helping build a code generation benchmark. '
                                          'The user provides code context and code solution, '
                                          'please refine the code.'
            }
        ]
        prompt = prompt_change_main_function(main_function, else_context)
        message.append({"role": "user", "content": prompt})

        index_x_message_list.append(
            (idx, target_dir_path + file_name, message)  # id, file_path, message
        )
    # # return tmp_dic, index_x_message_list
    library_name = 'pandas'
    count = 0
    res_list = asyncio.run(openai_model_conversation(index_x_message_list, setting_generate_test_cases))
    save_path = 'intermediate_result/%s_code_polish_%s.json' % (library_name, count)
    while os.path.exists(save_path):
        count += 1
        save_path = 'intermediate_result/%s_code_polish_%s.json' % (library_name, count)

    with open(save_path, 'w') as f:
        f.write(json.dumps(res_list))

    return index_x_message_list, res_list


def statistic(file_list):
    # with open('intermediate_result/all_test_case_10_0.json', 'r') as f:
    #     res_list = json.load(f)
    # statistic
        # Pandas 0-290
        # Numpy 291-510
        # Matplotlib 511-665
        # Tensorflow 666-710
        # Scipy 711-816
        # Sklearn 817-931
        # Pytorch 932-999
    # with open('selected_ground_truth_list.json', 'r') as f:
    #     selected_ground_truth_list = json.load(f)

    pandas_count = 0
    numpy_count = 0
    matplotlib_count = 0
    tensorflow_count = 0
    scipy_count = 0
    sklearn_count = 0
    pytorch_count = 0

    for file in file_list:
        id = int(file.split('/')[-1].split('_')[0])
    # for selected_file_path in selected_ground_truth_list:
    #     id = int(selected_file_path.split('/')[-1].split('_')[0])
        if id <= 290:
            pandas_count += 1
        elif id <= 510:
            numpy_count += 1
        elif id <= 665:
            matplotlib_count += 1
        elif id <= 710:
            tensorflow_count += 1
        elif id <= 816:
            scipy_count += 1
        elif id <= 931:
            sklearn_count += 1
        else:
            pytorch_count += 1
    res = {
        'pandas': pandas_count,
        'numpy': numpy_count,
        'matplotlib': matplotlib_count,
        'tensorflow': tensorflow_count,
        'scipy': scipy_count,
        'sklearn': sklearn_count,
        'pytorch': pytorch_count
    }
    return res

def test_case_statistic():
    test_case_dic = {}
    for i in range(10):
        with open('intermediate_result/filtered_test_cases/%s.json' % (i), 'r') as f:
            for line in f.readlines():
                content = json.loads(line)
                if content['file_path'] not in test_case_dic:
                    test_case_dic[content['file_path']] = sum(content['valid_test_output_list'])
                else:
                    test_case_dic[content['file_path']] += sum(content['valid_test_output_list'])
    return test_case_dic


def timeout_handler(signum, frame):
    raise TimeoutError("Execution timed out!")

# dataset generation
#   a. generate 10 test case input
#   b. use test case to filter ground truth (and get the test case output)
#   c. use ground truth to filter test case input (get valid test case status)
#   d. based on ground truth code, test cases, and valid test case status to generate code problem
#   e. use code problem to generate code
#   f. use test cases to measure the behaviour between ground truth code and generated code (filter code problem)
#   g. generate test case script
#   h. code repair to improve test case script
#   i. get the final dataset


# a. generate sample test case input
# and store in 'intermediate_result/%s_test_case_10_%s.json' % (library_name, count)
def generate_sample_test_case_input(library_name='all', ds1000orstackoverflow='ds1000', run_llm=False):
    # generate sample test case input for the ground truth code under path 'ground_truth_code_filtered_deduplicated/'
    # store in 'intermediate_result/%s_test_case_10_%s.json' % (library_name, count)
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'intermediate_search_result/DS1000_search/'
        target_dir_path = base_folder + 'ground_truth_code_filtered_deduplicated/'
        file_name_list = sorted(os.listdir(target_dir_path),
                                key=lambda name: tuple(map(int, name.rstrip(".py").split('_'))))
    else:
        base_folder = 'intermediate_search_result/stackoverflow_search/'
        target_dir_path = base_folder + 'ground_truth_code_filtered_deduplicated/'
        # file_name_list = sorted(os.listdir(target_dir_path),
        #                         key=lambda name: tuple(map(int, name.rstrip(".py").split('_')[1:])))
        file_name_list = sorted(os.listdir(target_dir_path),
                                key=lambda name: (name.split('_')[0], *map(int, name.rstrip(".py").split('_')[1:])))

    index_x_message_list = []
    tmp_dic = {}
    for idx in range(len(file_name_list)):
        file_name = file_name_list[idx]
        # if int(file_name.split('_')[0]) > 290:
        #     break
        with open(target_dir_path + file_name, 'r') as f:
            code = f.read()

        # get the main function
        code_line_list = code.split('\n')
        main_function = ''
        else_context = ''
        main_function_flag = False
        for line in code_line_list:
            if main_function_flag:
                main_function += line + '\n'
            else:
                if line != '# main code':
                    else_context += line + '\n'
            if line == '# main code':
                main_function_flag = True
        # index_x_message_list.append([file_name, main_function, else_context])
        tmp_dic[file_name] = [main_function, else_context]
        # # use gpt to generate test cases
        message = [
            {"role": "system", "content": 'You are a helpful programming assistant. '
                                          'You are helping build a code generation benchmark. '
                                          'The user provides a code, '
                                          'please generate test cases based on it.'
            }
        ]
        prompt = prompt_generate_sample_test_case_input(main_function, else_context)
        message.append({"role": "user", "content": prompt}),

        index_x_message_list.append(
            (idx, target_dir_path + file_name, message)  # id, file_path, message
        )
    if not run_llm:
        return tmp_dic, index_x_message_list
    else:
        count = 0
        res_list = asyncio.run(openai_model_conversation(index_x_message_list, setting_generate_test_cases))
        save_path = base_folder + 'intermediate_result/%s_test_case_10_%s.json' % (library_name, count)
        while os.path.exists(save_path):
            count += 1
            save_path = base_folder + 'intermediate_result/%s_test_case_10_%s.json' % (library_name, count)

        with open(save_path, 'w') as f:
            f.write(json.dumps(res_list))

        return tmp_dic, index_x_message_list, res_list

# generate test case output, and record test pass status
def generate_test_case_output(ground_truth_code, test_case_code):
    timeout_duration = 5
    signal.signal(signal.SIGALRM, timeout_handler)
    main_function_name, main_function_parameter_count = get_main_function_name_and_parameter_count(ground_truth_code)
    if main_function_name:
        if main_function_parameter_count > 1:
            exec_code = f'''
success_test_list = []
for test in test_input:
    try:
        {main_function_name}(*test)
        success_test_list.append(test)
    except:
        success_test_list.append('this is an invalid output')
        pass
        '''
        else:
            exec_code = f'''
success_test_list = []
for test in test_input:
    try:
        {main_function_name}(test)
        success_test_list.append(test)
    except:
        success_test_list.append('this is an invalid output')
        pass
        '''

        all_exec_code = ground_truth_code + '\n' + test_case_code + '\n' + exec_code

        # exec the test
        local_namespace = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_dir = os.getcwd()
            try:
                os.chdir(tmp_dir)
                # memory_limit_mb = 1000
                # resource.setrlimit(resource.RLIMIT_AS, (memory_limit_mb * 1024 * 1024, resource.RLIM_INFINITY))
                signal.alarm(timeout_duration)
                exec(all_exec_code, local_namespace)
                success_test_list = local_namespace['success_test_list']
                # test_case_list.append(success_test_list)
                signal.alarm(0)
                os.chdir(old_dir)
                if success_test_list:
                    return success_test_list
                    # selected_ground_truth_list.append(ground_truth_code_file_path)
                    # banned_ground_truth_list.pop()
                    # with open(selected_ground_truth_list_file_path, 'w') as f:
                    #     f.write(json.dumps(selected_ground_truth_list))
                    # with open(banned_ground_truth_list_file_path, 'w') as f:
                    #     f.write(json.dumps(banned_ground_truth_list))
            except Exception as e:
                signal.alarm(0)
                print(e, flush=True)
                os.chdir(old_dir)
                return None
                # success_test_list = []
                # test_case_list.append(success_test_list)
    return None

# b. filter test case based on ground truth code, and generate test case pass status
# and store in 'intermediate_result/filtered_test_cases/%s.json' % (i)
def test_case_filtering(ds1000orstackoverflow='ds1000', i=0):
    prefix = 'intermediate_search_result/stackoverflow_search/ground_truth_code_filtered_deduplicated/'
    banned_list = ['keras_12_95_0.py',
                  'keras_89_858_2.py',
                  'keras_91_917_2.py',
                  'matplotlib_2_24_0.py',
                  'pandas_26_97_0.py',
                  'pytorch_60_984_0.py',
                  'sklearn_47_149_0.py',
                  'sklearn_52_180_2.py',
                  'pytorch_44_430_3.py',
                  'tensorflow_30_235_0.py',
                  'tensorflow_55_566_2.py',
                  'tensorflow_61_552_1.py',
                  'pytorch_8_295_2.py',
                  'sklearn_58_5_1.py',
                  'tensorflow_55_566_1.py',
                  'tensorflow_65_882_8.py',
                  'keras_13_118_0.py',
                  'pytorch_3_61_1.py',
                  'pytorch_35_120_2.py',
                  'pytorch_49_391_2.py',
                  'sklearn_55_198_0.py',
                  'tensorflow_30_230_0.py',
                  'tensorflow_66_1021_6.py',
                  'tensorflow_82_831_0.py',
                  'pytorch_42_347_3.py',
                  'keras_102_1079_1.py',
                  'pytorch_27_120_2.py',
                  'keras_48_444_0.py',
                  'pytorch_3_61_0.py',
                  'scipy_40_127_3.py',
                  'tensorflow_73_1321_2.py',
                  'tensorflow_73_1330_6.py',
                  'matplotlib_40_514_2.py',
                  'matplotlib_69_761_0.py',
                  'matplotlib_115_1122_3.py',
                  'pytorch_8_309_3.py',
                  'pytorch_49_727_1.py',
                  'matplotlib_9_102_0.py',
                  'pandas_114_294_0.py']


    banned_list = [prefix+x for x in banned_list]
    test_case_dic = {}
    test_case_dic[i] = {}
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'intermediate_search_result/DS1000_search/'
    else:
        base_folder = 'intermediate_search_result/stackoverflow_search/'

    # with open('intermediate_result/filter_code_based_on_test_cases/selected_ground_truth_list_%s.json' % (i), 'r') as f:
    #     selected_ground_truth_list = json.load(f)

    with open(base_folder + 'intermediate_result/all_test_case_10_%s.json' % (i), 'r') as f:
        res_list = json.load(f)

    done_test_case_file_path_list = []
    if os.path.exists(base_folder + 'intermediate_result/filtered_test_cases/%s.json' % (i)):
        with open(base_folder + 'intermediate_result/filtered_test_cases/%s.json' % (i), 'r') as f:
            for line in f.readlines():
                done_test_case = json.loads(line)
                done_test_case_file_path_list.append(done_test_case['file_path'])
    if not os.path.exists(base_folder + 'intermediate_result/filtered_test_cases/'):
        os.mkdir(base_folder + 'intermediate_result/filtered_test_cases/')
    for res in res_list:
        if res['pid'] in done_test_case_file_path_list:
            continue
        if res['pid'] in banned_list:
            continue
        print(res['pid'], flush=True)
        with open(res['pid'], 'r') as f:
            ground_truth_code = f.read()
        test_case_code = extract_code(res['response'])

        # if len(test_case_code) != 1:
        #     test_case_code = ''
        # else:
        #     test_case_code = test_case_code[0]

        test_output_list = generate_test_case_output(add_matplotlib_agg(ground_truth_code), test_case_code)
        if test_output_list:
            tmp_list = []
            for test_output in test_output_list:
                if isinstance(test_output, str) and test_output == 'this is an invalid output':
                    tmp_list.append(0)
                else:
                    tmp_list.append(1)
            with open(base_folder + 'intermediate_result/filtered_test_cases/%s.json' % (i), 'a') as f:
                f.write(json.dumps({
                    'file_path': res['pid'],
                    'ground_truth_code': ground_truth_code,
                    'test_case_code': test_case_code,
                    'valid_test_output_list': tmp_list # 1 is valid, 0 is invalid
                }) + '\n')
                # test_case_dic[i][res['pid']] = test_output_list
        # if len(test_case_dic[i]) == 100:
        #     break
        # final_selected_ground_truth_dic[i] = selected_ground_truth_list


# c. filter ground truth code based on test case
def post_test_suite_generation(ds1000orstackoverflow='ds1000', idx=0):
    timeout_duration = 5
    signal.signal(signal.SIGALRM, timeout_handler)

    prefix = 'intermediate_search_result/stackoverflow_search/ground_truth_code_filtered_deduplicated/'
    # 0
    # banned_list = ['keras_12_95_0.py',
    #                'keras_77_744_1.py',
    #                'matplotlib_9_102_0.py',
    #                'pandas_26_97_0.py',
    #                'pytorch_8_295_2.py',
    #                'pytorch_60_984_0.py',
    #                'sklearn_47_149_0.py',
    #                'tensorflow_30_235_0.py',
    #                'tensorflow_55_566_1.py',
    #                'tensorflow_55_566_2.py',
    #                'tensorflow_65_882_8.py']
    # 1
    # banned_list = ['keras_48_444_0.py',
    #                'keras_91_917_2.py',
    #                'pandas_26_97_0.py',
    #                'tensorflow_30_235_0.py',
    #                'tensorflow_55_566_2.py',
    #                'tensorflow_61_552_1.py']
    # 2
    # banned_list = ['keras_13_118_0.py',
    #                'pytorch_27_97_0.py']
    # 3
    # banned_list = ['keras_13_118_0.py',
    #                'pandas_26_97_0.py',
    #                'pytorch_3_61_1.py',
    #                'pytorch_8_295_2.py',
    #                'pytorch_41_329_0.py',
    #                'pytorch_49_391_2.py',
    #                'sklearn_52_180_2.py',
    #                'sklearn_55_198_0.py',
    #                'tensorflow_30_230_0.py',
    #                'tensorflow_55_566_2.py',
    #                'tensorflow_66_1021_6.py',
    #                'tensorflow_82_831_0.py']
    # 4
    # banned_list = ['keras_12_95_0.py',
    #                'keras_13_118_0.py',
    #                'pandas_26_97_0.py',
    #                'pytorch_3_61_1.py',
    #                'pytorch_42_347_3.py',
    #                'tensorflow_55_566_2.py']
    # 5
    # banned_list = ['keras_102_1079_1.py',
    #                'pandas_26_97_0.py',
    #                'pytorch_3_61_1.py',
    #                'pytorch_27_120_2.py',
    #                'sklearn_55_198_0.py',
    #                'tensorflow_55_566_2.py',
    #                'tensorflow_66_1021_6.py']
    # 6
    # banned_list = ['keras_12_95_0.py',
    #                'keras_30_320_0.py',
    #                'pandas_26_97_0.py',
    #                'pytorch_42_347_3.py',
    #                'pytorch_60_984_0.py',
    #                'sklearn_47_149_0.py',
    #                'tensorflow_30_235_0.py',
    #                'tensorflow_55_566_1.py',
    #                'tensorflow_73_1330_6.py']
    # 7
    # banned_list = ['keras_91_917_2.py',
    #                'matplotlib_69_761_0.py',
    #                'pandas_26_97_0.py']
    # 8
    # banned_list = ['keras_30_320_0.py',
    #                'pandas_26_97_0.py',
    #                'pytorch_8_309_3.py',
    #                'pytorch_38_245_4.py',
    #                'pytorch_42_347_3.py',
    #                'pytorch_49_727_1.py',
    #                'pytorch_60_984_0.py',
    #                'sklearn_58_5_1.py',
    #                'tensorflow_55_566_2.py']
    # 9
    banned_list = ['keras_12_95_0.py',
                   'matplotlib_9_102_0.py',
                   'pandas_26_97_0.py',
                   'pandas_114_294_0.py',
                   'scipy_40_127_3.py',
                   'tensorflow_55_566_1.py',
                   'tensorflow_65_882_8.py']
    banned_list = [prefix + x for x in banned_list]
    # post_test_suite_generation = True
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'intermediate_search_result/DS1000_search/'
    else:
        base_folder = 'intermediate_search_result/stackoverflow_search/'

    # if post_test_suite_generation:
    #     idx = 9
    with open(base_folder + 'intermediate_result/all_test_case_10_%s.json' % (idx), 'r') as f:
        res_list = json.load(f)

    dir_path = base_folder + 'intermediate_result/filter_code_based_on_test_cases/'
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
    test_case_list = []
    selected_ground_truth_list_file_path = dir_path + 'selected_ground_truth_list_%s.json' % (idx)
    banned_ground_truth_list_file_path = dir_path + 'banned_ground_truth_list_%s.json' % (idx)

    if os.path.exists(selected_ground_truth_list_file_path):
        with open(selected_ground_truth_list_file_path, 'r') as f:
            selected_ground_truth_list = json.load(f)
    else:
        selected_ground_truth_list = []

    if os.path.exists(banned_ground_truth_list_file_path):
        with open(banned_ground_truth_list_file_path, 'r') as f:
            banned_ground_truth_list = json.load(f)
    else:
        banned_ground_truth_list = []


    for res in res_list:
        test_case = extract_code(res['response'])
        ground_truth_code_file_path = res['pid']
        if ground_truth_code_file_path in banned_list:
            continue

        if ground_truth_code_file_path in banned_ground_truth_list or \
                ground_truth_code_file_path in selected_ground_truth_list:
            continue
        print(ground_truth_code_file_path, flush=True)
        banned_ground_truth_list.append(ground_truth_code_file_path)
        with open(banned_ground_truth_list_file_path, 'w') as f:
            f.write(json.dumps(banned_ground_truth_list))

        # if '384_6_' in ground_truth_code_file_path or \
        #         '382_15_3.py' in ground_truth_code_file_path or \
        #         '504_11_2.py' in ground_truth_code_file_path or \
        #         '494_3_2.py' in ground_truth_code_file_path:
        #     continue

        # if len(test_case) != 1:
        #     test_case = ''
        # else:
        #     test_case = test_case[0]
        with open(ground_truth_code_file_path, 'r') as f:
            ground_truth_code = f.read()

        main_function_name, main_function_parameter_count = get_main_function_name_and_parameter_count(ground_truth_code)
        if main_function_name:
            if main_function_parameter_count > 1:
                exec_code = f'''
success_test_list = []
for test in test_input:
    try:
        {main_function_name}(*test)
        success_test_list.append(test)
    except:
        pass
'''
            else:
                exec_code = f'''
success_test_list = []
for test in test_input:
    try:
        {main_function_name}(test)
        success_test_list.append(test)
    except:
        pass
'''
            all_exec_code = add_matplotlib_agg(ground_truth_code) + '\n' + test_case + '\n' + exec_code
            # exec the test
            local_namespace = {}
            with tempfile.TemporaryDirectory() as tmp_dir:
                old_dir = os.getcwd()
                try:
                    os.chdir(tmp_dir)
                    # memory_limit_mb = 1000
                    # resource.setrlimit(resource.RLIMIT_AS, (memory_limit_mb * 1024 * 1024, resource.RLIM_INFINITY))
                    signal.alarm(timeout_duration)
                    exec(all_exec_code, local_namespace)
                    success_test_list = local_namespace['success_test_list']
                    test_case_list.append(success_test_list)
                    os.chdir(old_dir)
                    if success_test_list:
                        selected_ground_truth_list.append(ground_truth_code_file_path)
                        banned_ground_truth_list.pop()
                        with open(selected_ground_truth_list_file_path, 'w') as f:
                            f.write(json.dumps(selected_ground_truth_list))
                        with open(banned_ground_truth_list_file_path, 'w') as f:
                            f.write(json.dumps(banned_ground_truth_list))
                    signal.alarm(0)
                except:
                    signal.alarm(0)
                    success_test_list = []
                    test_case_list.append(success_test_list)
                    os.chdir(old_dir)


def ground_truth_code_filtering(ds1000orstackoverflow='ds1000'):
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'intermediate_search_result/DS1000_search/'
    else:
        base_folder = 'intermediate_search_result/stackoverflow_search/'
    final_selected_ground_truth_list = []
    for i in range(10):
        with open(base_folder + 'intermediate_result/filter_code_based_on_test_cases/selected_ground_truth_list_%s.json' % (i), 'r') as f:
            selected_ground_truth_list = json.load(f)
            final_selected_ground_truth_list += selected_ground_truth_list

    final_selected_ground_truth_list = list(set(final_selected_ground_truth_list))
    if ds1000orstackoverflow == 'ds1000':
        final_selected_ground_truth_list = sorted(final_selected_ground_truth_list, key=lambda name: tuple(map(int, name.split('/')[-1].rstrip(".py").split('_'))))

    else:
        final_selected_ground_truth_list = sorted(final_selected_ground_truth_list, key=lambda name: (name.split('/')[-1].split('_')[0], *map(int, name.split('/')[-1].rstrip(".py").split('_')[1:])))

    return final_selected_ground_truth_list


def prepare_sample_test_case(ds1000orstackoverflow='ds1000', library='numpy', generated_test_case_batch_index=0):
    # default using selected_ground_truth_list_0.json
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'intermediate_search_result/DS1000_search/'
        store_dir = 'new_dataset_candidate/ds1000/%s/sample_test_case/' % (library)

        store_path = store_dir + '%s.json' % (generated_test_case_batch_index)
        if not os.path.exists('new_dataset_candidate/ds1000/%s' % (library)):
            os.makedirs('new_dataset_candidate/ds1000/%s' % (library))

    else:
        base_folder = 'intermediate_search_result/stackoverflow_search/'
        store_dir = 'new_dataset_candidate/stackoverflow/%s/sample_test_case/' % (library)

        store_path = store_dir + '%s.json' % (generated_test_case_batch_index)
        if not os.path.exists('new_dataset_candidate/stackoverflow/%s' % (library)):
            os.makedirs('new_dataset_candidate/stackoverflow/%s' % (library))


    if not os.path.exists(store_dir):
        os.makedirs(store_dir)
    if os.path.exists(store_path):
        return

    test_cases_list = []
    with open(base_folder + 'intermediate_result/filter_code_based_on_test_cases/selected_ground_truth_list_%s.json' % (generated_test_case_batch_index), 'r') as f:
        selected_ground_truth_list = json.load(f)

    with open(base_folder + 'intermediate_result/filtered_test_cases/%s.json' % (generated_test_case_batch_index), 'r') as f:
        for line in f.readlines():
            content = json.loads(line)
            test_cases_list.append(content)


    tmp_list = []
    for i in range(len(selected_ground_truth_list)):
        ground_truth_code_file_path = selected_ground_truth_list[i]
        if ds1000orstackoverflow == 'ds1000':
            # select numpy
            # Pandas 0-290
            # Numpy 291-510
            # Matplotlib 511-665
            # Tensorflow 666-710
            # Scipy 711-816
            # Sklearn 817-931
            # Pytorch 932-999
            if 'intermediate_search_result/DS1000_search/' not in ground_truth_code_file_path:
                ground_truth_code_file_path = 'intermediate_search_result/DS1000_search/' + ground_truth_code_file_path

            pid = int(ground_truth_code_file_path.split('/')[-1].rstrip(".py").split('_')[0])

            if library == 'pandas':
                if pid > 290:
                    break
            elif library == 'numpy':
                if pid < 291:
                    continue
                elif pid > 510:
                    break
            elif library == 'matplotlib':
                if pid < 511:
                    continue
                elif pid > 665:
                    break
            elif library == 'tensorflow':
                if pid < 666:
                    continue
                elif pid > 710:
                    break
            elif library == 'scipy':
                if pid < 711:
                    continue
                elif pid > 816:
                    break
            elif library == 'sklearn':
                if pid < 817:
                    continue
                elif pid > 931:
                    break
            elif library == 'pytorch':
                if pid < 932:
                    continue
            else:
                break
        else:
            extracted_library = ground_truth_code_file_path.split('/')[-1].split('_')[0]
            if extracted_library != library:
                continue
        with open(ground_truth_code_file_path, 'r') as f:
            ground_truth_code = f.read()

        test_case = test_cases_list[i]

        tmp_dict = {
            'file_path': ground_truth_code_file_path,
            'ground_truth_code': ground_truth_code,
            'test_case': test_case,
        }
        tmp_list.append(tmp_dict)

    with open(store_path, 'w') as f:
        f.write(json.dumps(tmp_list))

# c.1 run this before d
def prepare_all_test_case(ds1000orstackoverflow='ds1000'):
    library_list = ['pandas', 'numpy', 'matplotlib', 'tensorflow', 'scipy', 'sklearn', 'pytorch', 'lightgbm', 'keras', 'seaborn']
    for i in range(10):
        for library in library_list:
            prepare_sample_test_case(ds1000orstackoverflow, library, i)


# d. generate code problem description, based on ground truth code, test cases, and valid test case status
def generate_code_problem_description(ds1000orstackoverflow='ds1000', library='numpy'):

    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'new_dataset_candidate/%s/%s/sample_test_case/' % ('ds1000', library)
        save_dir = 'new_dataset_candidate/%s/%s/' % ('ds1000', library)
    else:
        base_folder = 'new_dataset_candidate/%s/%s/sample_test_case/' % ('stackoverflow', library)
        save_dir = 'new_dataset_candidate/%s/%s/' % ('stackoverflow', library)

    if not os.path.exists(save_dir):
        os.mkdir(save_dir)

    index_x_message_list = []

    file_path_dic = {}
    for generated_test_case_batch_index in range(10):
        with open(base_folder + '%s.json' % (generated_test_case_batch_index), 'r') as f:
            tmp_list = json.load(f)
        for tmp_res in tmp_list:
            if tmp_res['file_path'] not in file_path_dic:
                file_path_dic[tmp_res['file_path']] = tmp_res
            else:
                if sum(tmp_res['test_case']['valid_test_output_list']) > \
                    sum(file_path_dic[tmp_res['file_path']]['test_case']['valid_test_output_list']):
                    file_path_dic[tmp_res['file_path']] = tmp_res

    # sort
    if ds1000orstackoverflow == 'ds1000':
        final_list = sorted(list(file_path_dic.values()), key=lambda x: tuple(map(int, x['file_path'].split('/')[-1].rstrip(".py").split('_'))))
    else:
        final_list = sorted(list(file_path_dic.values()), key=lambda x: (x['file_path'].split('/')[-1].split('_')[0], *map(int, x['file_path'].split('/')[-1].rstrip(".py").split('_')[1:])))

    # return final_list
    # get all the selected ground truth and test cases from 10 trials
    with open(save_dir + 'selected_ground_truth.json', 'w') as f:
        f.write(json.dumps(final_list))

    for idx in range(len(final_list)):
        file_path = final_list[idx]['file_path']

        message = [
            {"role": "system", "content": 'You are a helpful programming assistant. '
                                          'You are helping build a code generation benchmark. '
                                          'The user provides a ground truth code, test cases, '
                                          'and the valid status of the test cases'
                                          'please generate a code problem description based on them.'
            }
        ]
        prompt = prompt_generate_codeproblem(final_list[idx]['ground_truth_code'],
                                             final_list[idx]['test_case']['test_case_code'],
                                             final_list[idx]['test_case']['valid_test_output_list'])
        message.append({"role": "user", "content": prompt}),

        index_x_message_list.append(
            (idx, file_path, message)  # id, file_path, message
        )
    # return index_x_message_list

    # count = 0
    res_list = asyncio.run(openai_model_conversation(index_x_message_list, setting_generate_code_problem))

    save_path = save_dir + 'code_problem_description_generation.json'

    # while os.path.exists(save_path):
    #     # count += 1
    #     save_path = 'intermediate_result/%s_test_case_10_%s.json' % (library_name, count)

    with open(save_path, 'w') as f:
        f.write(json.dumps(res_list))
    return index_x_message_list, res_list


# e. use code problem to generate code,
# and store in 'new_dataset_candidate/%s/code_generation/%s.json' % (library, count)
def generate_code_based_on_code_problem_description(ds1000orstackoverflow='ds1000', library='numpy'):
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'new_dataset_candidate/%s/%s/' % ('ds1000', library)
        save_dir = 'new_dataset_candidate/%s/%s/code_generation/' % ('ds1000', library)
    else:
        base_folder = 'new_dataset_candidate/%s/%s/' % ('stackoverflow', library)
        save_dir = 'new_dataset_candidate/%s/%s/code_generation/' % ('stackoverflow', library)

    if not os.path.exists(save_dir):
        os.mkdir(save_dir)
    with open(base_folder + 'code_problem_description_generation.json', 'r') as f:
        res_list = json.load(f)

    index_x_message_list = []
    for idx in range(len(res_list)):
        code_problem_description = res_list[idx]['response']
        file_path = res_list[idx]['pid']

        message = []
        prompt = prompt_generate_solution(code_problem_description)
        message.append({"role": "user", "content": prompt}),

        index_x_message_list.append(
            (idx, file_path, message)  # id, file_path, message
        )

    count = 0
    res_list = asyncio.run(openai_model_conversation(index_x_message_list, setting_generate_code_problem))

    save_path = save_dir + '%s.json' % (count)

    while os.path.exists(save_path):
        count += 1
        save_path = save_dir + '%s.json' % (count)

    with open(save_path, 'w') as f:
        f.write(json.dumps(res_list))
    return index_x_message_list, res_list


# f. use test cases to measure the behaviour between ground truth code and generated code (filter code problem)
def measure_behaviour(ds1000orstackoverflow='ds1000', library='numpy', code_generation_id=0):
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'new_dataset_candidate/%s/%s/' % ('ds1000', library)
        save_path = 'new_dataset_candidate/%s/%s/behaviour_check/%s.json' % ('ds1000', library, code_generation_id)
    else:
        base_folder = 'new_dataset_candidate/%s/%s/' % ('stackoverflow', library)
        save_path = 'new_dataset_candidate/%s/%s/behaviour_check/%s.json' % ('stackoverflow', library, code_generation_id)

    timeout_duration = 5
    signal.signal(signal.SIGALRM, timeout_handler)
    passed_list = []
    status_list = []

    if not os.path.exists(base_folder + 'behaviour_check/'):
        os.mkdir(base_folder + 'behaviour_check/')
    if os.path.exists(save_path):
        with open(save_path, 'r') as f:
            for line in f.readlines():
                content = json.loads(line)
                if content[1]:
                    passed_list.append(content[0])
                status_list.append(content[0])
            # return passed_list

    with open(base_folder + 'code_generation/%s.json' % (code_generation_id), 'r') as f:
        generated_code_list = json.load(f)

    with open(base_folder + 'selected_ground_truth.json', 'r') as f:
        ground_truth_code_list = json.load(f)


    for idx in range(len(generated_code_list)):
        if idx in status_list:
            continue
        content = generated_code_list[idx]
        print('idx:', idx, flush=True)
        # if library == 'numpy' and (idx == 221 or idx == 28 or idx == 187):
        #     continue
        # if library == 'numpy' and code_generation_id == 5 and (idx == 267):
        #     continue
        # if library == 'matplotlib' and (idx == 54 or idx == 85):
        #     continue
        # if library == 'matplotlib' and (idx == 38):
        #     continue

        try:
            signal.alarm(timeout_duration)
            test_case_code = ground_truth_code_list[idx]['test_case']['test_case_code']
            generated_code = extract_code(content['response'])
            ground_truth_code = ground_truth_code_list[idx]['ground_truth_code']
            code_lines = generated_code.split('\n')
            new_code_lines = []
            for line in code_lines:
                if '"__main__"' in line:
                    break
                new_code_lines.append(line)
            generated_code = '\n'.join(new_code_lines)
            function_names = get_function_names(generated_code)
            signal.alarm(0)
        except:
            with open(save_path, 'a') as f:
                f.write('%s\n' % (json.dumps([idx, False])))
            signal.alarm(0)
            continue
        if len(function_names) == 1:
            # main_function_name = function_names[0]
            try:
                signal.alarm(timeout_duration)
                generated_code_test_output_list = generate_test_case_output(add_matplotlib_agg(generated_code), test_case_code)
                ground_truth_code_test_output_list = generate_test_case_output(add_matplotlib_agg(ground_truth_code), test_case_code)
                same_test_count = 0
                for test_i in range(len(ground_truth_code_test_output_list)):
                    if ground_truth_code_test_output_list[test_i] == generated_code_test_output_list[test_i]:
                        same_test_count += 1

                if same_test_count < len(ground_truth_code_test_output_list) and same_test_count > 0:
                    # print(generated_code_test_output_list)

                    passed_list.append(idx)
                    with open(save_path, 'a') as f:
                        f.write('%s\n' % (json.dumps([idx, True])))
                elif (same_test_count == len(ground_truth_code_test_output_list) and
                      (library == 'matplotlib' or library == 'seaborn')):
                    passed_list.append(idx)
                    with open(save_path, 'a') as f:
                        f.write('%s\n' % (json.dumps([idx, True])))
                else:
                    with open(save_path, 'a') as f:
                        f.write('%s\n' % (json.dumps([idx, False])))
                signal.alarm(0)
            except:
                with open(save_path, 'a') as f:
                    f.write('%s\n' % (json.dumps([idx, False])))
                signal.alarm(0)
                pass
        else:
            continue


    return passed_list


def behavior_check_between_generated_code_and_ground_truth_code(ds1000orstackoverflow='ds1000', library='numpy', total=10):
    final_list = []
    for i in range(total): # default 10 times
        behaviour_check_selected_list = measure_behaviour(ds1000orstackoverflow, library, i)
        final_list += behaviour_check_selected_list

    return sorted(list(set(final_list)))


# g. generate test case script
def generate_test_case_script(ds1000orstackoverflow='ds1000', library='numpy'):
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'new_dataset_candidate/%s/%s/' % ('ds1000', library)
    else:
        base_folder = 'new_dataset_candidate/%s/%s/' % ('stackoverflow', library)

    if not os.path.exists(base_folder + 'test_case_script_generation/'):
        os.makedirs(base_folder + 'test_case_script_generation/')

    # for the list below, the ground truth and code problems are ok
    selected_problem_list = behavior_check_between_generated_code_and_ground_truth_code(ds1000orstackoverflow, library)

    with open(base_folder + 'code_problem_description_generation.json', 'r') as f:
        code_problem_list = json.load(f)

    with open(base_folder + 'selected_ground_truth.json', 'r') as f:
        ground_truth_code_list = json.load(f)

    index_x_message_list = []
    for idx in selected_problem_list:
        file_path = ground_truth_code_list[idx]['file_path']
        message = [
            {"role": "system", "content": 'You are a helpful programming assistant. '
                                          'You are helping build a code generation benchmark. '
                                          'The user provides a ground truth code, code problem, sample test cases, '
                                          'and the valid status of these test cases. '
                                          'Please generate a test case generation script based on them.'
            }
        ]

        # content = generated_code_list[idx]
        test_case_code = ground_truth_code_list[idx]['test_case']['test_case_code']
        valid_test_output_list = ground_truth_code_list[idx]['test_case']['valid_test_output_list']
        # # generated_code = extract_code(content['response'])
        ground_truth_code = ground_truth_code_list[idx]['ground_truth_code']
        code_problem = extract_codeproblem(code_problem_list[idx]['response'])

        prompt = prompt_generate_testcase_script_from_solution_and_codeproblem(ground_truth_code, code_problem,
                                                                               test_case_code, valid_test_output_list)

        message.append({"role": "user", "content": prompt})
        index_x_message_list.append(
            (idx, file_path, message)  # id, file_path, message
        )

    # return index_x_message_list
    res_list = asyncio.run(openai_model_conversation(index_x_message_list, setting_generate_code_problem))

    count = 0
    save_path = base_folder + 'test_case_script_generation/%s.json' % (count)

    while os.path.exists(save_path):
        count += 1
        save_path = base_folder + 'test_case_script_generation/%s.json' % (count)

    with open(save_path, 'w') as f:
        f.write(json.dumps(res_list))
    return index_x_message_list, res_list


def test_generated_test_case_script(ground_truth_code, test_case_script, get_input_output=False):
    # Target: generate test case that ground truth code can be all pass
    timeout_duration = 10
    signal.signal(signal.SIGALRM, timeout_handler)

    exec_code = prepare_exec_code(ground_truth_code, test_case_script, get_input_output)
    if get_input_output:
        # get more detail about the test case input when raising error
        local_namespace = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_dir = os.getcwd()
            try:
                signal.alarm(timeout_duration)
                os.chdir(tmp_dir)
                # memory_limit_mb = 1000
                # resource.setrlimit(resource.RLIMIT_AS, (memory_limit_mb * 1024 * 1024, resource.RLIM_INFINITY))
                exec(exec_code, local_namespace)
                os.chdir(old_dir)
                signal.alarm(0)
                test_case_output_list = local_namespace['test_case_output_list']
                test_case_input_list = local_namespace['test_case_input_list']
            except Exception as e:
                signal.alarm(0)
                test_case_output_list = []
                test_case_input_list = []
                print(e)
                os.chdir(old_dir)
        # find the first error output
        if test_case_output_list and 0 in test_case_output_list:
            index = test_case_output_list.index(0)
            error_test_input = test_case_input_list[index]
            return error_test_input

    else:
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_dir = os.getcwd()
            try:
                os.chdir(tmp_dir)
                test_file = 'test_case_script_test.py'
                with open(test_file, 'w') as f:
                    f.write(exec_code)
                output = subprocess.run(["python", test_file], capture_output=True, text=True, timeout=10)
                os.chdir(old_dir)
            except subprocess.TimeoutExpired:
                os.chdir(old_dir)
                return 'Timeout'
            except:
                os.chdir(old_dir)
                return 'Unknown error.'

        if output.returncode != 0:
            # update the test case script based on the error
            error_info = output.stderr
            return error_info

        # # subprocess to judge whether all the test input can be passed
        # test_file = 'test/test_case_script_test.py'
        # with open(test_file, 'w') as f:
        #     f.write(exec_code)
        # try:
        #     output = subprocess.run(["python", test_file], capture_output=True, text=True, timeout=10)
        # except subprocess.TimeoutExpired:
        #     return 'Timeout'
        # except:
        #     return 'Unknown error.'
        #
        # if output.returncode != 0:
        #     # update the test case script based on the error
        #     error_info = output.stderr
        #     return error_info
    return ''

# h. improve test case script
def update_generated_test_case_script(ds1000orstackoverflow='ds1000', library='numpy', threshold=5):
    # iteratively update test case script, max = 5
    # adjust the test case script based on the error

    # selected_problem_list = behavior_check_between_generated_code_and_ground_truth_code(library)
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'new_dataset_candidate/%s/%s/' % ('ds1000', library)
    else:
        base_folder = 'new_dataset_candidate/%s/%s/' % ('stackoverflow', library)


    with open(base_folder + 'selected_ground_truth.json', 'r') as f:
        ground_truth_code_list = json.load(f)

    # get the lastest version of test case script
    count = 0
    target_test_case_script_path = base_folder + 'test_case_script_generation/%s.json' % (count)
    while os.path.exists(target_test_case_script_path):
        count += 1
        target_test_case_script_path = base_folder + 'test_case_script_generation/%s.json' % (count)
    if count != 0:
        target_test_case_script_path = base_folder + 'test_case_script_generation/%s.json' % (count-1)
    else:
        target_test_case_script_path = base_folder + 'test_case_script_generation/%s.json' % (0)

    print('current test case generation script: %s' % target_test_case_script_path, flush=True)

    with open(target_test_case_script_path, 'r') as f:
        test_case_script_list = json.load(f)

    if count > threshold:
        with open(target_test_case_script_path, 'r') as f:
            res_list = json.load(f)
        return None, res_list

    if count == threshold:
        save_path = base_folder + 'test_case_script_generation/%s.json' % (5)
        # apply final checking
        final_test_case_script_res_list = []
        for test_case_script_res in test_case_script_list:
            idx = test_case_script_res['index']
            print(idx)
            if ('updated_test_case_script' in test_case_script_res and
                    test_case_script_res['updated_test_case_script'] == 0):
                final_test_case_script_res_list.append(test_case_script_res)
                continue
            ground_truth_code = ground_truth_code_list[idx]['ground_truth_code']
            test_case_script = extract_code(test_case_script_res['response'])
            if idx == 248 and library == 'matplotlib' and ds1000orstackoverflow == 'ds1000':
                test_case_script_res['updated_test_case_script'] = 1
                final_test_case_script_res_list.append(test_case_script_res)
                continue
            if (idx == 22 or idx == 103 or idx == 148 or idx == 202 or idx == 366) and library == 'matplotlib' and ds1000orstackoverflow != 'ds1000':
                test_case_script_res['updated_test_case_script'] = 1
                final_test_case_script_res_list.append(test_case_script_res)
                continue
            error_info = test_generated_test_case_script(add_matplotlib_agg(ground_truth_code), test_case_script, False)
            if error_info:
                test_case_script_res['updated_test_case_script'] = 1
                final_test_case_script_res_list.append(test_case_script_res)
            else:
                test_case_script_res['updated_test_case_script'] = 0
                final_test_case_script_res_list.append(test_case_script_res)
        with open(save_path, 'w') as f:
            f.write(json.dumps(final_test_case_script_res_list))
        return

    index_x_message_list = []
    for test_case_script_res in test_case_script_list:
        idx = test_case_script_res['index']
        print('idx', idx, flush=True)
        if 'updated_test_case_script' in test_case_script_res and test_case_script_res['updated_test_case_script'] == 0:
            print('pass')
            continue
        if idx == 248 and library == 'matplotlib' and ds1000orstackoverflow == 'ds1000':
            continue
        if (idx == 22 or idx == 103 or idx == 148 or idx == 202 or idx == 366) and library == 'matplotlib' and ds1000orstackoverflow != 'ds1000':
            continue
        file_path = ground_truth_code_list[idx]['file_path']
        # update test case script generation prompt
        message = [
            {"role": "system", "content": 'You are a helpful programming assistant. '
                                          'You are helping build a code generation benchmark. '
                                          'The user provide the ground truth code, '
                                          'previous version of test case generation script, '
                                          'and error information.'
                                          'Please update and generate a new test case generation script '
                                          'to make the generated test cases more suitable for the ground truth code.'
            }
        ]

        ground_truth_code = ground_truth_code_list[idx]['ground_truth_code']
        test_case_script = extract_code(test_case_script_res['response'])

        error_info = test_generated_test_case_script(add_matplotlib_agg(ground_truth_code), test_case_script, False)
        if error_info:
            test_case_input = test_generated_test_case_script(add_matplotlib_agg(ground_truth_code), test_case_script, True)

            prompt = prompt_update_testcase_script(ground_truth_code, test_case_script, error_info, test_case_input)

            message.append({"role": "user", "content": prompt})
            index_x_message_list.append(
                (idx, file_path, message)  # id, file_path, message
            )

        # print(prompt)
    # return index_x_message_list
    print('Start run LLM to generate new scripts.', flush=True)
    res_list = asyncio.run(openai_model_conversation(index_x_message_list, setting_generate_code_problem))

    save_path = base_folder + 'test_case_script_generation/%s.json' % (count)
    while os.path.exists(save_path):
        count += 1
        save_path = base_folder + 'test_case_script_generation/%s.json' % (count)

    # mix the updated test case
    count_s = 0
    final_res_list = []
    updated_pid_list = [x['pid'] for x in res_list]
    for test_case_script_res in test_case_script_list:
        if test_case_script_res['pid'] in updated_pid_list:
            tmp_res = res_list[updated_pid_list.index(test_case_script_res['pid'])]
            tmp_res['updated_test_case_script'] = 1
            final_res_list.append(tmp_res)
        else:
            tmp_res = test_case_script_res
            tmp_res['updated_test_case_script'] = 0
            final_res_list.append(tmp_res)
            count_s += 1

    with open(save_path, 'w') as f:
        f.write(json.dumps(final_res_list))
    print(len(final_res_list), count_s, flush=True)
    return index_x_message_list, final_res_list


def collect_dataset_components(ds1000orstackoverflow='ds1000', library='numpy'):
    if ds1000orstackoverflow == 'ds1000':
        base_folder = 'new_dataset_candidate/%s/%s/' % ('ds1000', library)
    else:
        base_folder = 'new_dataset_candidate/%s/%s/' % ('stackoverflow', library)

    count = 0
    target_test_case_script_path = base_folder + 'test_case_script_generation/%s.json' % (count)
    while os.path.exists(target_test_case_script_path):
        count += 1
        target_test_case_script_path = base_folder + 'test_case_script_generation/%s.json' % (count)
    if count != 0:
        target_test_case_script_path = base_folder + 'test_case_script_generation/%s.json' % (count-1)
    else:
        target_test_case_script_path = base_folder + 'test_case_script_generation/%s.json' % (0)

    print('current test case generation script: %s' % target_test_case_script_path, flush=True)

    try:
        with open(target_test_case_script_path, 'r') as f:
            test_case_script_list = json.load(f)

        with open(base_folder + 'code_problem_description_generation.json', 'r') as f:
            code_problem_list = json.load(f)

        with open(base_folder + 'selected_ground_truth.json', 'r') as f:
            ground_truth_code_list = json.load(f)

        tmp_res = {
            'ground_truth_code_list': ground_truth_code_list,
            'code_problem_list': code_problem_list,
            'test_case_script_list': test_case_script_list
        }

        return tmp_res
    except:
        tmp_res = {
            'ground_truth_code_list': [],
            'code_problem_list': [],
            'test_case_script_list': []
        }
        return tmp_res

# i. get the final dataset
def get_dataset(library='numpy'):
    final_dataset = []
    # test case script
    # get the lastest version of test case script
    # ds1000
    ds1000_dataset = collect_dataset_components('ds1000', library)
    stackoverflow_dataset = collect_dataset_components('stackoverflow', library)


    pid = 0
    for res in ds1000_dataset['test_case_script_list']:
        idx = res['index']
        test_case_script = extract_code(res['response'])
        ground_truth_code = ds1000_dataset['ground_truth_code_list'][idx]['ground_truth_code']
        code_problem = extract_codeproblem(ds1000_dataset['code_problem_list'][idx]['response'])
        if res['updated_test_case_script'] == 1:
            test_case_script_valid = 0
            continue
        else:
            test_case_script_valid = 1
        final_dataset.append({
            'pid': pid,
            'code_problem': code_problem,
            'ground_truth_code': ground_truth_code,
            'test_case_script': test_case_script,
            'test_case_script_valid': test_case_script_valid
        })
        pid += 1

    for res in stackoverflow_dataset['test_case_script_list']:
        idx = res['index']
        test_case_script = extract_code(res['response'])
        ground_truth_code = stackoverflow_dataset['ground_truth_code_list'][idx]['ground_truth_code']
        code_problem = extract_codeproblem(stackoverflow_dataset['code_problem_list'][idx]['response'])
        if res['updated_test_case_script'] == 1:
            test_case_script_valid = 0
            continue
        else:
            test_case_script_valid = 1
        final_dataset.append({
            'pid': pid,
            'code_problem': code_problem,
            'ground_truth_code': ground_truth_code,
            'test_case_script': test_case_script,
            'test_case_script_valid': test_case_script_valid
        })
        pid += 1

    return final_dataset


# convert into files
def convert_into_files():
    library_list = ['numpy', 'pandas', 'matplotlib', 'scipy', 'sklearn',
                    'matplotlib', 'seaborn', 'tensorflow', 'pytorch', 'keras', 'lightgbm']
    for library in library_list:
        dataset = get_dataset(library)
        base_dir = 'DS-bench/'
        if not os.path.exists(base_dir + '%s/' % (library)):
            os.makedirs(base_dir + '%s/' % (library))
        for x in dataset:
            # if x['test_case_script_valid'] == 0:
            #     continue
            if not os.path.exists(base_dir + '%s/' % (library) + str(x['pid'])):
                os.makedirs(base_dir + '%s/' % (library) + str(x['pid']))
            save_dir = base_dir + '%s/' % (library) + str(x['pid']) + '/'

            with open(save_dir + 'code_problem.txt', 'w') as f:
                f.write(x['code_problem'])

            with open(save_dir + 'test_case_script.py', 'w') as f:
                f.write(x['test_case_script'])

            with open(save_dir + 'ground_truth_code.py', 'w') as f:
                f.write(x['ground_truth_code'])

            with open(save_dir + 'test_case_script_valid.txt', 'w') as f:
                f.write(str(x['test_case_script_valid']))


def convert_into_list():
    final_dataset_list = []
    library_list = ['pandas', 'numpy', 'matplotlib', 'tensorflow', 'scipy',
                    'sklearn',  'pytorch', 'keras',  'seaborn',  'lightgbm']
    count_dic = {}

    for library in library_list:
        dataset = get_dataset(library)
        count_dic[library] = len(dataset)
        for x in dataset:
            x['library'] = library
            x['pid'] = library + '_' + str(x['pid'])
        final_dataset_list += dataset

    with open('DS-bench/dataset.json', 'w') as f:
        f.write(json.dumps(final_dataset_list))

    return final_dataset_list, count_dic


if __name__ == '__main__':
    generate_sample_test_case_input(library_name='all', ds1000orstackoverflow='ds1000', run_llm=False)
    # test_case_filtering(ds1000orstackoverflow='ds1000', i=0)
    # post_test_suite_generation(ds1000orstackoverflow='ds1000', idx=0)
    # generate_code_problem_description(ds1000orstackoverflow='ds1000', library='numpy')
    # prepare_all_test_case(ds1000orstackoverflow='ds1000')
    # generate_code_based_on_code_problem_description(ds1000orstackoverflow='ds1000', library='numpy')
    # measure_behaviour(ds1000orstackoverflow='ds1000', library='numpy', code_generation_id=0)
    # generate_test_case_script(ds1000orstackoverflow='ds1000', library='numpy')
    # update_generated_test_case_script(ds1000orstackoverflow='ds1000', library='numpy', threshold=5)
    # get_dataset(library='numpy')