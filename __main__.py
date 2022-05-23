"""
- Raw Data
    - Wikipedia articles in HTML format
    - Each equation within a <math> tag. Within is a <semantics> tag. Should have 3 children:
        - <mrow>: display representation, maybe multiple of these per equation?
        - <annotation-xml encoding="MathML-Content">: OPT representation, generated by LaTeXML
        - <annotation encoding="application/x-tex">: LaTeX representation
    - TODO: verify which equations follow the expected format
- Processed Data
    - Each article should have a mix of raw text and formulas
        - The formulas should be surrounded by special characters indicating start and stop
        - The formulas can be stored in separate files, referenced by identifiers in the processed article
        - Each formula should be represented as an OPT
            - Seems like TangentCFT (https://github.com/BehroozMansouri/TangentCFT) can be used for processing these
            - Each symbol will be associated with a type, as well as a position in the tree (level and position)
            - Should be stored in depth-first order
    - Vocabulary
        - Break into operator, variable, and number types
        - Type will indicate to model whether we have a leaf or not, and if we need to use numerical encoding
- Model
    - Based on GPT-2
    - Input
        - For text tokens, use pretrained text embeddings
            - Add learnable text identifier embedding
        - For formula tokens, need to encode: that it's a formula token, its embedding (or numeric encoding), and its position in the tree
    - Output
        - Differentiate between text and formula outputs
"""

import argparse

from pre_process import process_wikipedia_data
from analyze_data import analyze_data
from training import pretrain, evaluate_lm, test_lm
from utils import TrainOptions, initialize_seeds, device

def main():
    if device.type == "cuda":
        print("Running on GPU")
    else:
        print("No GPU found")

    initialize_seeds(221)

    parser = argparse.ArgumentParser("MathGPT")
    # Modes
    parser.add_argument("--preprocess", action="store_true", help="Process raw Wikipedia data and save to JSON files; generate raw vocab file")
    parser.add_argument("--analyze_data", action="store_true", help="Produce stats on pre-processed dataset")
    parser.add_argument("--pretrain", action="store_true", help="Pre-train LM")
    parser.add_argument("--evaluate_lm", action="store_true", help="Evaluate LM performance on test set")
    parser.add_argument("--test_lm", action="store_true", help="Run qualitative test on LM")
    # Config
    parser.add_argument("--name", help="Name of current model/experiment, used for saving/loading model and config")
    parser.add_argument("--epochs", type=int, help="Maximum number of training epochs")
    parser.add_argument("--batch_size", type=int, help="Maximum number of sequences per batch")
    parser.add_argument("--grad_accum_batches", type=int, help="Number of batches to accumulate gradients for")
    parser.add_argument("--max_seq_len", type=int, help="Maximum length, in tokens, of any sequence")
    parser.add_argument("--stride", type=int, help="Stride for computing perplexity with sliding context window")

    args = parser.parse_args()
    arg_dict = {arg: val for arg, val in vars(args).items() if val is not None}

    if args.preprocess:
        process_wikipedia_data()
    if args.analyze_data:
        analyze_data()
    if args.pretrain:
        pretrain(args.name, TrainOptions(arg_dict))
    if args.evaluate_lm:
        evaluate_lm(args.name, arg_dict)
    if args.test_lm:
        test_lm(args.name, "data/Grade_(slope).json")

if __name__ == "__main__":
    main()
