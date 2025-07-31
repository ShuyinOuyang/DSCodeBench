# Set up

First, you need to set up several accounts and environments.

### GitHub REST API

Our benchmark construction pipeline needs to search code by using the GitHub search engine.
GitHub offers its official [REST API](https://docs.github.com/en/rest/about-the-rest-api).

You need to get a GitHub token like `token ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` and fill it into the file `personal_token/github_token_0.json`


### OpenAI API

Our benchmark construction code relies on LLM, especially the GPT series.
Configure your own OpenAI info in file `personal_token/gpt_info.json`. 
If you are still a free user of the OpenAI model API, please configure your account as pay-as-you-go before running the script, otherwise it's likely to reach the free trial limitation.

### experiment environment (for evaluation only)

Please use the following command to create a Conda environment from the `environment.yml`.

```sh
conda env create -f environment.yml
```

or install the dependencies from `requirements.txt`

```sh
pip install -r requirements.txt
```


**DON'T upload your script with your GitHub token or openai.key to the public repository!!!!!!!!!!!**

# Benchmark Construction

## Code Task Scope Determination

We choose NumPy, Pandas, SciPy, Scikit-learn, TensorFlow, PyTorch, Matplotlib, Seaborn, Keras, and LightGBM as our target libraries.

## Ground Truth Code Construction

### Collect Seed code

In this step, you could run the script `get_data_from_stackoverflow.py` to collect the information from Stack Overflow.
For the reference code in [DS-1000](https://github.com/xlang-ai/DS-1000), you can get the dataset from [here](https://huggingface.co/datasets/xlangai/DS-1000).

**!!Update: if your code returns Response 403, you should configure your request with the header!!**


### Sourcing code from GitHub

In this step, we run the following script to get the initial search result from GitHub.


```sh
python github_code_search.py -l torch -s stackoverflow
```

-l (--library): choose library (only if args.source=='stackoverflow')
-s (--source): choose seed code source ('ds1000' or 'stackoverflow')

### Code filtering (part of it)

In this step, we filter the code with the following script.

```sh
python filter_code_file.py -l torch -s stackoverflow
```

### Context reconstruction (+ the rest of the code filtering)

In this step, we reconstruct the code with its context in the repository (for file-level, especially).
First, we do the context completion by using the following command.

```sh
python code_context_completion.py -f generate_ground_truth_code -s stackoverflow
```

Second, we do the compilation filtering with the following command.

```sh
python code_context_completion.py -f compilation_filter -s stackoverflow -l numpy
```

Third, we do the deduplication with the following command.

```sh
python code_context_completion.py -f deduplication -s stackoverflow
```

### Test Case Generation & Problem Description Generation

The main logic of test case generation and problem description generation is in the file `dataset_generation.py`.
I need a bit of manual effort in some steps, so we recommend tuning the code based on the need.
The main logic functions are listed in the "main" function.



# Benchmark Evaluation

### Generate Solution

We use the following command to generate solutions for DS-bench and DS-1000:

```sh
python LLM_generate_solution.py -b ds_bench
```


### Run Test

For DS-bench, we use the following script to run the evaluation.

```sh
bash run.sh "$model" "$input_file"
```

For DS-1000, we use the following script to run the evaluation.

```sh
bash run_ds1000.sh "$model" "$input_file"
```

