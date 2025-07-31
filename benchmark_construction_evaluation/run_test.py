import json
import ast
import signal
import tempfile
import os
import re
import argparse
import asyncio
import aiofiles
from asyncio import Semaphore

def extract_code(text):
    pattern = r'```(?:[\w]+)?\n(.*?)```'
    code_blocks = re.findall(pattern, text, re.DOTALL)
    if code_blocks:
        return code_blocks[0]
    else:
        return ''

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

def get_library_from_code(code):
    classified_code = classify_code_ast(code)
    import_libs = []
    for import_line in classified_code['imports']:
        import_libs += extract_imports(import_line.strip())
    return import_libs

def timeout_handler(signum, frame):
    raise TimeoutError("Execution timed out!")

def get_main_function_name_and_parameter_count_brief(code):
    try:
        tree = ast.parse(code)
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef)]
        function_name = functions[-1].name if functions else None
        function_parameter_count = len(functions[-1].args.args)
        return function_name, function_parameter_count
    except:
        return None, None

def add_random_seed_code(import_libs, random_seed):
    random_seed_code = ''
    for import_lib in import_libs:
        if 'random' in import_lib[0]:
            random_seed_code += 'import random\nrandom.seed(%s)\n' % random_seed
        elif import_lib[0] in ['numpy', 'pandas', 'scipy', 'matplotlib', 'matplotlib.pyplot', 'seaborn']:
            random_seed_code += 'import numpy as np\nnp.random.seed(%s)\n' % random_seed
        elif 'torch' in import_lib[0]:
            random_seed_code += 'import random\nimport numpy as np\nimport torch\ntorch.manual_seed(%s)\nrandom.seed(%s)\nnp.random.seed(%s)\n' % (
                random_seed, random_seed, random_seed)
        elif import_lib[0] in ['tensorflow', 'keras']:
            random_seed_code += 'import tensorflow as tf\nimport random\nimport numpy as np\ntf.random.set_seed(%s)\nrandom.seed(%s)\nnp.random.seed(%s)\n' % (
                random_seed, random_seed, random_seed)
    return random_seed_code

def add_random_seed_into_functions(code, random_seed):

    class AddRandomStateTransformer(ast.NodeTransformer):
        def __init__(self):
            self.api_list = [
                'RatioUniforms', 'RandomForestClassifier', 'RandomForestRegressor', 'KFold',
                'StratifiedKFold', 'LinearSVC', 'MLPRegressor', 'train_test_split', 'make_regression',
                'make_classification'
            ]

        def visit_Call(self, node):
            node.args = [self.visit(arg) for arg in node.args]
            node.keywords = [self.visit(keyword) for keyword in node.keywords]

            for randomness_api in self.api_list:
                if (
                    (isinstance(node.func, ast.Name) and node.func.id == randomness_api) or
                    (isinstance(node.func, ast.Attribute) and node.func.attr == randomness_api)
                ):
                    # Special case for KFold
                    if randomness_api == 'KFold' or randomness_api == 'StratifiedKFold':
                        shuffle_exist = False
                        for keyword in node.keywords:
                            if keyword.arg == 'shuffle':
                                keyword.value = ast.Constant(value=True)
                                shuffle_exist = True
                            if keyword.arg == 'random_state':
                                keyword.value = ast.Constant(value=random_seed)
                                break
                        else:
                            if not shuffle_exist:
                                node.keywords.append(ast.keyword(arg='shuffle', value=ast.Constant(value=True)))
                            node.keywords.append(ast.keyword(arg='random_state', value=ast.Constant(value=random_seed)))
                    else:
                        for keyword in node.keywords:
                            if keyword.arg == 'random_state':
                                keyword.value = ast.Constant(value=random_seed)
                                break
                        else:
                            node.keywords.append(ast.keyword(arg='random_state', value=ast.Constant(value=random_seed)))

            return node

    tree = ast.parse(code)
    transformer = AddRandomStateTransformer()
    modified_tree = transformer.visit(tree)
    return ast.unparse(modified_tree)

def get_additional_code(code, is_matplotlib_or_seaborn, test_case_number=0):
    if test_case_number == 0:
        test_case_number = ''
    else:
        test_case_number = str(test_case_number)

    main_function_name, function_parameter_count = get_main_function_name_and_parameter_count_brief(code)
    if is_matplotlib_or_seaborn:
        if function_parameter_count is None or function_parameter_count <= 2:
            additional_code = f'''
from PIL import Image
import numpy as np

test_cases = test_case_input_generator({test_case_number})
output_list = []
for i in range(len(test_cases)):
    {main_function_name}(test_cases[i])
    img = np.array(Image.open("output.png").convert("RGB"))
    output_list.append(img)
'''
        else:
            additional_code = f'''
from PIL import Image
import numpy as np

test_cases = test_case_input_generator({test_case_number})
output_list = []
for i in range(len(test_cases)):
    {main_function_name}(*test_cases[i])
    img = np.array(Image.open("output.png").convert("RGB"))
    output_list.append(img)
'''
    else:
        if function_parameter_count == 1:
            additional_code = f'''
test_cases = test_case_input_generator({test_case_number})
output_list = []
for i in range(len(test_cases)):
    output_list.append({main_function_name}(test_cases[i]))
'''
        else:
            additional_code = f'''
test_cases = test_case_input_generator({test_case_number})
output_list = []
for i in range(len(test_cases)):
    output_list.append({main_function_name}(*test_cases[i]))
'''

    return additional_code

def prepare_exec_code(code, test_case_script, is_ground_truth_code=True, random_seed=42, is_matplotlib_or_seaborn=False, test_case_number=0):

    import_libs = get_library_from_code(code)
    try:
        code = add_random_seed_into_functions(code, random_seed)
    except:
        code = code
    code = add_matplotlib_agg(code)
    test_case_script = add_random_seed_into_functions(test_case_script, random_seed)
    if is_ground_truth_code:
        import_libs += get_library_from_code(test_case_script)
    import_libs = list(set(import_libs))
    random_seed_code = add_random_seed_code(import_libs, random_seed)
    additional_code = get_additional_code(code, is_matplotlib_or_seaborn, test_case_number)
    return code + '\n\n' + test_case_script + '\n\n' + random_seed_code + '\n\n' + additional_code

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

def get_code_output_list(exec_code, time_limit, test_case_input_list=None):
    if time_limit:
        timeout_duration = 200
        signal.signal(signal.SIGALRM, timeout_handler)
    if test_case_input_list:
        local_namespace = {
            'test_cases': test_case_input_list,
        }
    else:
        local_namespace = {}
    with tempfile.TemporaryDirectory() as tmp_dir:
        old_dir = os.getcwd()
        try:
            if time_limit:
                signal.alarm(timeout_duration)
            os.chdir(tmp_dir)
            # memory_limit_mb = 1000
            # resource.setrlimit(resource.RLIMIT_AS, (memory_limit_mb * 1024 * 1024, resource.RLIM_INFINITY))
            exec(exec_code, local_namespace)
            os.chdir(old_dir)
            if time_limit:
                signal.alarm(0)

            test_case_output_list = local_namespace['output_list']
            test_case_input_list = local_namespace['test_cases']
        except Exception as e:
            print(e)
            if time_limit:
                signal.alarm(0)
            test_case_output_list = []
            test_case_input_list = []
            os.chdir(old_dir)
    return test_case_input_list, test_case_output_list


def get_exec_output(ground_truth_code, test_solution_code, test_case_script, time_limit=True,
                    is_matplotlib_or_seaborn=False, test_case_number=0, random_seed=42):
    # run on ground truth
    exec_code_ground_truth = prepare_exec_code(ground_truth_code, test_case_script,
                                               is_ground_truth_code=True,
                                               random_seed=random_seed,
                                               is_matplotlib_or_seaborn=is_matplotlib_or_seaborn,
                                               test_case_number=test_case_number)


    test_case_input_list, ground_truth_code_output_list = get_code_output_list(exec_code_ground_truth, time_limit=False)

    # run on test solution
    exec_code_test_solution = prepare_exec_code(test_solution_code, test_case_script,
                                                is_ground_truth_code=True,
                                                random_seed=random_seed,
                                                is_matplotlib_or_seaborn=is_matplotlib_or_seaborn,
                                                test_case_number=test_case_number)
    test_case_input_list1, test_solution_output_list = get_code_output_list(exec_code_test_solution, time_limit=time_limit)

    return test_case_input_list, ground_truth_code_output_list, test_solution_output_list


def exec_test(result, ans):
    import numpy as np
    import pandas as pd
    import math
    import torch
    import scipy
    import tensorflow as tf
    import keras
    import lightgbm as lgb
    import sklearn
    # print(result, flush=True)
    # print(ans, flush=True)

    if isinstance(result, tuple):
        # print('isinstance tuple', flush=True)
        assert len(result) == len(ans)
        for i in range(len(result)):
            assert type(result[i]) == type(ans[i])
            exec_test(result[i], ans[i])
    elif isinstance(result, sklearn.base.BaseEstimator):
        # print('isinstance sklearn.base.BaseEstimator', flush=True)
        assert str(result.get_params()) == str(ans.get_params())
    elif isinstance(result, lgb.basic.Booster):
        # print('isinstance lgb.basic.Booster', flush=True)
        assert result.dump_model() == ans.dump_model()
    elif isinstance(result, lgb.basic.Dataset):
        # print('isinstance lgb.basic.Dataset', flush=True)
        assert np.allclose(result.get_data(), ans.get_data(), equal_nan=True)
    elif isinstance(result, tf.Tensor):
        # print('isinstance tf.tensor', flush=True)
        assert np.allclose(result.numpy(), ans.numpy(), equal_nan=True)
    elif isinstance(result, tf.Variable):
        # print('isinstance tf.Variable', flush=True)
        assert np.allclose(result.numpy(), ans.numpy(), equal_nan=True)
    elif isinstance(result, scipy.sparse.bsr_matrix):
        # print('isinstance scipy.sparse.bsr_matrix', flush=True)
        assert result.shape == ans.shape
        assert result.nnz == ans.nnz
        assert np.allclose(result.indices, ans.indices)
        assert np.allclose(result.indptr, ans.indptr)
        assert np.allclose(result.data, ans.data)
    elif isinstance(result, scipy.sparse.coo_matrix):
        # print('isinstance scipy.sparse.coo_matrix', flush=True)
        assert np.allclose(result.row, ans.row)
        assert np.allclose(result.col, ans.col)
        assert np.allclose(result.data, ans.data)
        assert result.shape == ans.shape
        assert result.nnz == ans.nnz
    elif isinstance(result, scipy.sparse.csc_matrix):
        # print('isinstance scipy.sparse.csc_matrix', flush=True)
        assert result.shape == ans.shape
        assert result.nnz == ans.nnz
        assert np.allclose(result.indices, ans.indices)
        assert np.allclose(result.indptr, ans.indptr)
        assert np.allclose(result.data, ans.data)
    elif isinstance(result, scipy.sparse.csr_matrix):
        # print('isinstance scipy.sparse.csr_matrix', flush=True)
        assert result.shape == ans.shape
        assert result.nnz == ans.nnz
        assert np.allclose(result.indices, ans.indices)
        assert np.allclose(result.indptr, ans.indptr)
        assert np.allclose(result.data, ans.data)
    elif isinstance(result, scipy.sparse.dia_matrix):
        # print('isinstance scipy.sparse.dia_matrix', flush=True)
        assert result.shape == ans.shape
        assert result.nnz == ans.nnz
        assert np.allclose(result.data, ans.data)
        assert np.allclose(result.offsets, ans.offsets)
    elif isinstance(result, scipy.sparse.dok_matrix):
        # print('isinstance scipy.sparse.dok_matrix', flush=True)
        assert result.shape == ans.shape
        assert result.nnz == ans.nnz
        result_dict, ans_dict  = dict(result), dict(ans)
        for i in result_dict:
            exec_test(result_dict[i], ans_dict[i])
    elif isinstance(result, scipy.sparse.lil_matrix):
        # print('isinstance scipy.sparse.lil_matrix', flush=True)
        assert result.shape == ans.shape
        assert result.nnz == ans.nnz
        assert all(np.allclose(result.rows[i], ans.rows[i]) for i in range(result.shape[0]))
        assert all(np.allclose(result.data[i], ans.data[i]) for i in range(result.shape[0]))
    elif isinstance(result, dict):
        # print('isinstance dict', flush=True)
        for i in result:
            exec_test(result[i], ans[i])
    elif isinstance(result, list):
        # print('isinstance list', flush=True)
        assert len(result) == len(ans)
        for i in range(len(result)):
            exec_test(result[i], ans[i])
    elif isinstance(result, np.ma.MaskedArray):
        # print('isinstance np.ma.MaskedArray', flush=True)
        np.ma.allclose(result, ans)
    elif isinstance(result, np.ndarray):
        # print('isinstance np.ndarray', flush=True)
        assert np.allclose(result, ans, equal_nan=True)
    elif isinstance(result, torch.Tensor):
        # print('isinstance torch.Tensor', flush=True)
        torch.allclose(result, ans, equal_nan=True)
    elif isinstance(result, torch.nn.Sequential):
        # print('isinstance torch.nn.Sequential', flush=True)
        assert len(result) == len(ans)
        for p1, p2 in zip(result.parameters(), ans.parameters()):
            assert torch.allclose(p1, p2, equal_nan=True)
    elif isinstance(result, torch.nn.Linear):
        # print('isinstance torch.nn.Linear', flush=True)
        assert torch.allclose(result.weight, ans.weight)
        assert torch.allclose(result.bias, ans.bias)
    elif isinstance(result, scipy.stats._multivariate.multivariate_normal_frozen):
        # print('isinstance scipy.stats._multivariate.multivariate_normal_frozen', flush=True)
        np.allclose(result.mean, ans.mean)
        np.allclose(result.cov, ans.cov)
        assert result.dim == ans.dim
        assert result.random_state == ans.random_state
    elif isinstance(result, pd.DataFrame):
        # print('isinstance pd.DataFrame', flush=True)
        pd.testing.assert_frame_equal(result, ans)
    elif isinstance(result, float):
        # print('isinstance float', flush=True)
        math.isclose(result, ans)
    elif isinstance(result, pd.Series):
        # print('isinstance pd.Series', flush=True)
        pd.testing.assert_series_equal(result, ans)

    elif isinstance(result, keras.models.Model):
        # print('isinstance keras.models.Model', flush=True)

        def normalize_layer_names(obj):
            if isinstance(obj, list):
                return [normalize_layer_names(item) for item in obj]
            elif isinstance(obj, str):
                # Match anything like name_N -> name
                return re.sub(r'_(\d+)$', '', obj)
            else:
                return obj
        def normalize_config(config):
            keys_to_remove = ['name', 'dtype', 'trainable']
            keys_to_modify = ['inbound_nodes', 'input_layers']
            def recursive_clean(obj):
                if isinstance(obj, dict):
                    for key in list(obj.keys()):
                        if key in keys_to_remove:
                            obj.pop(key)
                        elif key in keys_to_modify:
                            if obj[key]:
                                obj[key] = normalize_layer_names(obj[key])
                        else:
                            recursive_clean(obj[key])
                elif isinstance(obj, list):
                    for item in obj:
                        recursive_clean(item)
            recursive_clean(config)
            return config
        config1 = normalize_config([layer.get_config() for layer in result.layers])
        config2 = normalize_config([layer.get_config() for layer in ans.layers])
        # print(config1)
        # print(config2)
        assert config1 == config2
    elif isinstance(result, torch.utils.data.TensorDataset):
        # print('isinstance torch.utils.data.TensorDataset', flush=True)
        assert len(result.tensors) == len(ans.tensors)

        for i, (t1, t2) in enumerate(zip(result.tensors, ans.tensors)):
            assert torch.allclose(t1, t2, equal_nan=True)

    else:
        # print('isinstance else', flush=True)
        assert result == ans
    return 1

def exec_test_img(result, ans):
    from skimage.metrics import structural_similarity as ssim
    ssim_r, _ = ssim(result[:, :, 0], ans[:, :, 0], full=True)
    ssim_g, _ = ssim(result[:, :, 1], ans[:, :, 1], full=True)
    ssim_b, _ = ssim(result[:, :, 2], ans[:, :, 2], full=True)
    ssim_avg = (ssim_r + ssim_g + ssim_b) / 3
    assert ssim_avg > 0.5
    return 1

def evaluate_outputs(test_case_input_list, ground_truth_code_output_list, test_solution_output_list, is_matplotlib_or_seaborn=False):
    evaluation_result_list = []
    # print(test_case_input_list, flush=True)
    for i in range(len(test_case_input_list)):
        try:
            ground_truth_code_output = ground_truth_code_output_list[i]
            test_solution_output = test_solution_output_list[i]
            # print('ground_truth_code', type(ground_truth_code_output), flush=True)
            # print('test_solution', type(test_solution_output), flush=True)
            if type(ground_truth_code_output) == type(test_solution_output):
                exec_status = exec_test(ground_truth_code_output, test_solution_output)
                evaluation_result_list.append(exec_status)
            else:
                evaluation_result_list.append(0)
        except:
            evaluation_result_list.append(0)

    return evaluation_result_list


async def evaluate_single_case(id, content, response_list, save_file, test_case_number, semaphore):
    async with semaphore:
        print(id, flush=True)
        solution_code = extract_code(response_list[id]['response'])
        is_plot = 'output.png' in content['ground_truth_code']

        inputs, output_gt, output_test = get_exec_output(content['ground_truth_code'], solution_code, content['test_script'],
                                                         is_matplotlib_or_seaborn=is_plot,
                                                         test_case_number=test_case_number,
                                                         random_seed=42)

        evaluation_result = evaluate_outputs(inputs, output_gt, output_test)
        evaluation_dic = {'id': id, 'evaluation_result': evaluation_result}

        async with aiofiles.open(save_file, 'a') as f:
            await f.write(json.dumps(evaluation_dic) + '\n')


async def run_evaluation(model='gpt-4o', test_case_number=200, target_file='generation_all_t_0_0.json'):
    async with aiofiles.open(f'{model}/{target_file}', 'r') as f:
        response_list = json.loads(await f.read())

    content_list = []
    async with aiofiles.open('DS_bench.json', 'r') as f:
        async for line in f:
            content_list.append(json.loads(line))

    save_file = f'{model}/{target_file.replace("generation", "evaluation_result")}'
    evaluated_ids = []
    if os.path.exists(save_file):
        async with aiofiles.open(save_file, 'r') as f:
            async for line in f:
                evaluated_ids.append(json.loads(line)['id'])
    else:
        async with aiofiles.open(save_file, 'w') as f:
            await f.write('')

    semaphore = Semaphore(1)  # Limit concurrency to 10 simultaneous tasks

    tasks = [evaluate_single_case(id, content, response_list, save_file, test_case_number, semaphore)
             for id, content in enumerate(content_list) if id not in evaluated_ids]

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--model", type=str, choices=['gpt-3.5-turbo', 'gpt-4o', 'gpt-4o-mini',
                                                            'deepseek-coder-1.3b-instruct', 'deepseek-coder-6.7b-instruct', 'deepseek-coder-33b-instruct', 'DeepSeek-Coder-V2-Lite-Instruct',
                                                            'Qwen2.5-Coder-7B-Instruct', 'Qwen2.5-Coder-14B-Instruct', 'Qwen2.5-Coder-32B-Instruct'], required=True)
    parser.add_argument("-n", "--test_case_number", type=int, default=200)
    parser.add_argument("-f", "--target_file", type=str, default='generation_all_t_0_0.json')
    args = parser.parse_args()
    asyncio.run(run_evaluation(args.model, args.test_case_number, args.target_file))