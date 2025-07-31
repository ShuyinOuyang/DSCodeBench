#!/bin/bash -l
#SBATCH --output=/scratch/users/%u/%j.out
#SBATCH --job-name=sy_run_evaluation

MODEL_NAME="$1"
FILE_NAME="$2"

if [ -z "$MODEL_NAME" ] || [ -z "$FILE_NAME" ]; then
    echo "Usage: $0 <model_name> <file_name>"
    exit 1
fi


while true; do
    echo "Running run_test.py with model: $MODEL_NAME and file: $FILE_NAME..."
    python run_test.py -m "$MODEL_NAME" -f "$FILE_NAME"
done