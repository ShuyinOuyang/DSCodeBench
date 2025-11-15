# DSCodeBench: A Realistic Benchmark for Data Science Code Generation

<p align="center">
  <img src="fig/logo.png" style="height: 10em"/>
</p>

<p align="center">
    <a href="https://www.python.org/">
        <img alt="Build" src="https://img.shields.io/badge/Python-3.8+-1f425f.svg?color=purple">
    </a>
</p>

##  👋 Overview
**DSCodeBench** is a new benchmark designed to evaluate LLMs on complex and realistic data science code generation tasks. 
It comprises 1,000 meticulously crafted problems derived from real-world GitHub repositories, spanning ten widely-used Python data science libraries.

Compared to the state-of-the-art benchmark DS-1000, DSCodeBench offers a more challenging and representative evaluation suite, featuring:
- Longer and more realistic code solutions
- Broader library coverage
- Clearer and better-structured problem descriptions
- Stronger test suites

To build DSCodeBench, we developed a robust pipeline that includes task selection, ground truth code construction, test case generation, and problem description synthesis. This process is enhanced with a thorough manual review to ensure accuracy and improve evaluation reliability.

Experimental results demonstrate that DSCodeBench exhibits reliable scaling behavior: larger models consistently outperform smaller ones. For example, the best-performing model, GPT-4o, achieves a pass@1 score of 0.392, indicating there is still significant room for improvement in realistic data science code generation.

We hope DSCodeBench provides a rigorous and trustworthy foundation for advancing LLM-based data science programming.

## ⬇️ Benchmark

You can directly download the benchmark from `benchmark` folder.

<p align="center">
  <img src="fig/distribution.png">
</p>

<p align="center">
  <img src="fig/benchmark_comparison.png">
</p>

## 🚀 Benchmark Construction Pipeline & Evaluation


You can find the full code for benchmark construction and evaluation in the [`benchmark_construction_evaluation`](https://github.com/ShuyinOuyang/DS_bench/tree/main/benchmark_construction_evaluation) folder.
**A detailed README** is also provided in that directory for further guidance.

<p align="center">
  <img src="fig/overview.png">
</p>

## 💻 Evaluation Detail

### Random Control
**Random Seed** In our evaluation framework, we set the random seed to 42 to maintain the consistency of identical experiments.
For some libraries, such as NumPy, Tensorflow, and Pytorch, we can easily set the random seed by using their default API function, like np.random.seed(),tf.random.set_seed(), and torch.manual_seed().
But there are also libraries, such as Sklearn, which do not have specific API functions to control the global random seed. Instead, they control randomness by setting the value of random_state in the API functions, such as RandomForestClassifier(random_state=None).
For these situations, we explicitly reset the value of random_state to 42 by iterating through the AST nodes of the code.

**Temperature**  In our experiment, we set the temperature to 0.2. For each code task, we let the LLM generate a response 3 times to make the result more robust.

## 📍 Experimental Results

Results from our experiments are available in the  `experiment_results` folder.

<p align="center">
  <img src="fig/experiment_result.png">
</p>



