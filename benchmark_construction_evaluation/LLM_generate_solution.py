import argparse
import os
import asyncio
import json
import signal
import subprocess
import tempfile
from util import *


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
    # 'model': 'gpt-4o-mini', # gpt-4o-mini-2024-07-18
    'model': 'gpt-4o', # gpt-4o-2024-0806
    'temperature': 0.2,
}


def prompt_generate_solution(code_problem_description):
    prompt = ('Please generate Python3 solution for the following code problem description:\n\n'
              '# Code problem description #\n'
              '%s\n\n'
              '# Response #\n'
              'The return should follow the following format (replace {} with the solution). '
              'Do not generate additional code, such as "__main__" block.'
              'Solution:\n{}' % (code_problem_description))

    return prompt

def prompt_generate_ds1000_solution(code_problem_description):
    prompt = ('Please generate Python3 solution for the following code problem description:\n\n'
              '# Code problem description #\n'
              '%s\n\n'
              '# Response #\n'
              'The return should follow the following format (replace {} with the solution). '
              'Do not generate additional code, such as "__main__" block.'
              'Code should end with \'</code>\\nEND SOLUTION\'\n'
              'Solution:\n{}' % (code_problem_description))
    return prompt

def load_dataset():
    res_list = []
    with open('../DS_bench.json', 'r') as f:
        for line in f.readlines():
            content = json.loads(line)
            res_list.append({
                'problem_id': content['problem_id'],
                'library': content['library'],
                'code_problem': content['code_problem'],
                'ground_truth_code': content['ground_truth_code'],
                'test_script': content['test_script'],
            })
    return res_list


def generate_code_based_on_code_problem_description(library='all'):
    # save_dir = 'DS_bench_evaluation_result/'
    save_dir = 'DS_bench_evaluation_result/' + setting_generate_code['model'] + '/'
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    dataset = load_dataset()

    index_x_message_list = []
    for idx in range(len(dataset)):
        code_problem_description = dataset[idx]['code_problem']
        problem_id = dataset[idx]['problem_id']

        message = []
        prompt = prompt_generate_solution(code_problem_description)
        message.append({"role": "user", "content": prompt}),

        index_x_message_list.append(
            (idx, problem_id, message)  # id, file_path, message
        )
    count = 0
    res_list = asyncio.run(openai_model_conversation(index_x_message_list, setting_generate_code)) # temperature=0

    save_path = save_dir + 'generation_%s_t_%s_%s.json' % (library, setting_generate_code['temperature'], count)

    while os.path.exists(save_path):
        count += 1
        save_path = save_dir + 'generation_%s_t_%s_%s.json' % (library, setting_generate_code['temperature'], count)

    with open(save_path, 'w') as f:
        f.write(json.dumps(res_list))
    return index_x_message_list, res_list

def generate_DS1000_code_based_on_code_problem_description(library='all'):
    save_dir = 'DS-1000/' + setting_generate_code['model'] + '/'
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    dataset = [json.loads(l) for l in gzip.open("ds1000.jsonl.gz", "rt").readlines()]
    index_x_message_list = []
    for idx in range(len(dataset)):
        code_problem_description = dataset[idx]['prompt']
        problem_id = '%s_%s' % (dataset[idx]['metadata']['library'].lower(), idx)

        message = []
        prompt = prompt_generate_ds1000_solution(code_problem_description)
        message.append({"role": "user", "content": prompt}),

        index_x_message_list.append(
            (idx, problem_id, message)  # id, file_path, message
        )
    count = 0
    res_list = asyncio.run(openai_model_conversation(index_x_message_list, setting_generate_code)) # temperature=0

    save_path = save_dir + 'generation_%s_t_%s_%s.json' % (library, setting_generate_code['temperature'], count)

    while os.path.exists(save_path):
        count += 1
        save_path = save_dir + 'generation_%s_t_%s_%s.json' % (library, setting_generate_code['temperature'], count)

    with open(save_path, 'w') as f:
        f.write(json.dumps(res_list))
    return index_x_message_list, res_list


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-b",
        "--benchmark",
        type=str,
        choices=['ds_bench', 'ds1000'],
        help="Choose seed code source",
        required=True,
    )

    args = parser.parse_args()
    if args.benchmark == 'ds_bench':
        generate_code_based_on_code_problem_description()
    elif args.benchmark == 'ds1000':
        generate_DS1000_code_based_on_code_problem_description()