import json
import gzip
import os
import subprocess
import re
import tempfile
import argparse
import asyncio

def response2code(response, prompt, stop_sign='</code>\nEND SOLUTION'):
    # extract generated code completion from response
    code_template = re.compile('```.*\n([\s\S]+?)\n```', re.M)
    code_template2 = re.compile('<code>.*\n([\s\S]+?)\n</code>', re.M | re.I)
    match_res = code_template.findall(response)
    match_res2 = code_template2.findall(response)
    if len(match_res) > 0:
        tmp_code = match_res[-1]
    elif len(match_res2) > 0:
        tmp_code = match_res2[-1]
    else:
        tmp_code = response.split(stop_sign)[0]
    # remove the duplicated code that appears once in prompt
    prompt_line_list = prompt.split('A:')[-1].split('\n')
    # prompt_line_list = [i.strip() for i in prompt_line_list]
    variable_names = []
    for line in prompt_line_list:
        if '=' in line:
            if line.split('=')[0].strip() != 'result' and '... #' not in line:
                variable_names.append(line.split('=')[0].strip())
    # print(variable_names)
    # print(prompt_line_list)
    stop_sign_list = stop_sign.split('\n')
    return_code = ''
    assign_flag = False
    for index, line in enumerate(tmp_code.split('\n')):
        if line.split('=')[0].strip() in variable_names:
            continue
        if line.strip().startswith('print('):
            continue
        # # if not assign_flag and '=' in line and line.strip().endswith(','):
        # #     assign_flag = True
        if line.strip().endswith(','):
            assign_flag = True
            continue
        if assign_flag:
            assign_flag = False
            continue
        if (line.strip() not in prompt_line_list) and (line.strip() not in stop_sign_list):
            return_code += line + '\n'
    # for index, line in enumerate(tmp_code.split('\n')):
        # if only_diff:
        #     if line.strip() not in prompt_line_list:
        #         return_code += line.strip() + '\n'
        # else:
        # if (line.strip() not in prompt_line_list) and (line.strip() not in stop_sign_list):
        #     return_code += line + '\n'
    # change the final return with 'result' as variable

    # return_code_line_list = return_code.strip().split('\n')
    # last_line = 'result = ' + return_code_line_list[-1].split('=', 1)[-1]
    # return_code_line_list[-1] = last_line
    # return_code = '\n'.join(return_code_line_list)
    return return_code


def test_code(pid, problem_dic, response_dic, ds1000):
    with tempfile.TemporaryDirectory() as tmp_dir:
        old_dir = os.getcwd()
        os.chdir(tmp_dir)
        code = response2code(response_dic['response'], ds1000[pid]['prompt'])

        test_program = (
                problem_dic['code_context'] + '\n'
                # + f'code = {repr(get_solution(id))}\n'
                + f'code = {repr(code)}\n'
                + 'test_execution(code)\n'
                + ('test_string(code)\n' if 'test_string(' in problem_dic['code_context'] else '\n')
        )
        test_file = 'test_demo_%s.py' % (pid)
        with open(test_file, 'w') as f:
            f.write(test_program)
        try:
            output = subprocess.run(["python", test_file], capture_output=True, text=True, timeout=120)
        except:
            output = None
    os.chdir(old_dir)
    return output, code, test_program


def run_test(model, target_file_name):
    # model = 'gpt-4o-mini'
    #     model = 'gpt-4o'
    #     target_file_name = 'generation_all_t_0.2_0.json'

    with open('DS-1000/%s/' % (model) + target_file_name, 'r') as f:
        response_list = json.load(f)
    ds1000 = [json.loads(l) for l in gzip.open("ds1000.jsonl.gz", "rt").readlines()]
    output_list = []

    for response_dic in response_list:
        if 'index' not in response_dic:
            id = 'problem_id'
        else:
            id = 'index'
        print(response_dic[id], flush=True)
        problem_dic = ds1000[response_dic[id]]
        output, code, test_program = test_code(response_dic[id], problem_dic, response_dic, ds1000)
        output_list.append(output)
        with open('DS-1000/%s/' % (model) + target_file_name.replace('generation', 'evaluation'), 'a') as f:
            if output:
                f.write(json.dumps({
                    'args': output.args,
                    'returncode': output.returncode,
                    'stderr': output.stderr,
                    'stdout': output.stdout,
                    'generated_code': code,
                    'test_program': test_program
                }) + '\n')
            else:
                f.write(json.dumps({
                    'args': '',
                    'returncode': 1,
                    'stderr': 'Timeout',
                    'stdout': '',
                    'generated_code': code,
                    'test_program': test_program
                }) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--model", type=str, choices=['gpt-3.5-turbo', 'gpt-4o', 'gpt-4o-mini',
                                                            'deepseek-coder-1.3b-instruct', 'deepseek-coder-6.7b-instruct', 'deepseek-coder-33b-instruct', 'DeepSeek-Coder-V2-Lite-Instruct',
                                                            'Qwen2.5-Coder-7B-Instruct', 'Qwen2.5-Coder-14B-Instruct', 'Qwen2.5-Coder-32B-Instruct'], required=True)
    parser.add_argument("-f", "--target_file", type=str, default='generation_all_t_0_0.json')
    args = parser.parse_args()
    run_test(args.model, args.target_file)
