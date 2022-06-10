from typing import List, Callable, Tuple, Optional, Dict
import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm
from sklearn import metrics
# from nltk.translate.bleu_score import corpus_bleu
from nlgeval import compute_metrics
# from rouge_score import rouge_scorer, scoring

from loading import Dataset, Collator, trim_batch
from mathGPT.constants import DownstreamTask
from model_math_gpt import MathGPTBase, MathGPTLM, MathGPTClassifier
from generate import get_most_likely_predictions, generate
from decode import decode_batch
from utils import TrainOptions
from constants import PADDING_TOKEN_ID, CollatedBatch

def evaluate_lm(model: MathGPTLM, dataset: Dataset, options: TrainOptions):
    """
    Calculate perplexity: e ^ ((1/n) * nll)
    Algorithm from https://huggingface.co/docs/transformers/perplexity
    """
    # TODO: unit test
    data_loader = DataLoader(
        dataset,
        collate_fn=Collator(),
        batch_size=1, # Only 1 sequence can be processed at a time to recover NLL from the cross-entropy loss (because of padding complications)
    )
    total_loss = 0.0
    num_batches = 0
    stride = options.stride or options.max_seq_len
    with torch.no_grad():
        nlls: List[torch.Tensor] = []
        total_sequence_length = 0
        for batch in tqdm(data_loader):
            sequence_length = batch["token_ids"].shape[1]
            total_sequence_length += sequence_length

            # Get the sum of the NLL for each token in the sequence, using the stride method
            # Region to left of split point is just for context with no NLL computed, and region to the right contribues to running NLL
            for split_point in range(0, sequence_length, stride):
                start_idx = max(split_point + stride - options.max_seq_len, 0)
                end_idx = min(split_point + stride, sequence_length)
                target_len = end_idx - split_point # This is equal to stride length except maybe shorter for the last iteration
                sub_seq_batch = trim_batch(batch, start_idx, end_idx)
                # Set targets to left of split point to padding so their NLL is not computed
                labels = torch.clone(sub_seq_batch["token_ids"])
                labels[:, :-target_len] = PADDING_TOKEN_ID
                # Run model on batch sub-sequence with altered targets
                loss = model(sub_seq_batch, labels=labels)[0]
                total_loss += loss.detach().cpu().numpy()
                num_batches += 1
                # Loss is average NLL over all tokens in the sequence, multiply by number of targets to undo average and retrieve sum
                nlls.append(loss * target_len)
        perplexity = torch.exp(torch.sum(torch.stack(nlls)) / total_sequence_length)
    # TODO: see why loss is different here vs. evaluate_lm_accuracy
    return total_loss / num_batches, f"Perplexity: {perplexity:.3f}"

def process_model_output(model: MathGPTBase, dataset: Dataset, task: Optional[DownstreamTask], options: TrainOptions, output_accumulator: Callable[[Tuple, CollatedBatch], None]):
    data_loader = DataLoader(
        dataset,
        collate_fn=Collator(task),
        batch_size=options.batch_size
    )
    total_loss = 0.0
    num_batches = 0
    model.eval()
    with torch.no_grad():
        for batch in tqdm(data_loader):
            model_output = model(batch)
            total_loss += model_output[0].detach().cpu().numpy()
            num_batches += 1
            output_accumulator(model_output, batch)
    return total_loss / num_batches

def evaluate_lm_accuracy(model: MathGPTLM, dataset: Dataset, task: Optional[DownstreamTask], options: TrainOptions):
    """
    Calculate per-token prediction accuracy
    """
    # TODO: unit test
    all_predictions = []
    all_labels = []
    def accumulate_predictions(model_output, batch: CollatedBatch):
        type_preds, token_preds = get_most_likely_predictions(model_output[1])
        # For predictions and targets, stack types and tokens in last dimension
        type_preds = type_preds[:, :-1].contiguous().view(-1).detach().cpu().numpy()
        token_preds = token_preds[:, :-1].contiguous().view(-1).detach().cpu().numpy()
        predictions = np.stack([type_preds, token_preds], axis=-1)
        type_targets = batch["token_types"][:, 1:].contiguous().view(-1).detach().cpu().numpy()
        labels = batch["gen_labels"] if batch["gen_labels"] is not None else batch["token_ids"]
        token_targets = labels[:, 1:].contiguous().view(-1).detach().cpu().numpy()
        targets = np.stack([type_targets, token_targets], axis=-1)
        mask = token_targets != PADDING_TOKEN_ID
        all_predictions.append(predictions[mask])
        all_labels.append(targets[mask])

    loss = process_model_output(model, dataset, task, options, accumulate_predictions)

    all_preds_np = np.concatenate(all_predictions, axis=0)
    all_labels_np = np.concatenate(all_labels, axis=0)
    # Get indices where both type and token match
    match = all_preds_np == all_labels_np
    match = match[:, 0] & match[:, 1]
    accuracy = sum(match) / len(match)
    return loss, f"Accuracy: {accuracy:.3f}"

def evaluate_gen_task(model: MathGPTLM, dataset: Dataset, task: DownstreamTask, options: TrainOptions):
    # TODO: unit test
    data_loader = DataLoader(
        dataset,
        collate_fn=Collator(task),
        batch_size=1 # Only process one sequence at a time since prompts may have different lengths
    )
    all_labels: List[CollatedBatch] = []
    all_predictions: List[CollatedBatch] = []
    with torch.no_grad():
        for batch in tqdm(data_loader):
            split_point = batch["prompt_lengths"][0]
            gen_batch = trim_batch(batch, 0, split_point)
            generate(model, gen_batch, options)
            all_predictions.append(trim_batch(gen_batch, split_point, options.max_seq_len))
            all_labels.append(trim_batch(batch, split_point, options.max_seq_len))

    num_exact_match = sum(
        1 for pred, label in zip(all_predictions, all_labels)
        if pred["token_ids"].shape == label["token_ids"].shape and torch.all(pred["token_ids"] == label["token_ids"]) and torch.all(pred["token_types"] == label["token_types"])
    )
    accuracy = num_exact_match / len(all_labels)
    pred_text_batch = [decode_batch(pred, dataset.text_tokenizer)[0].replace("\n", " ") for pred in all_predictions]
    label_text_batch = [decode_batch(label, dataset.text_tokenizer)[0].replace("\n", " ") for label in all_labels]
    pred_filename = "preds.txt"
    label_filename = "labels.txt"
    with open(pred_filename, "w", encoding="utf-8") as pred_file:
        pred_file.write("\n".join(pred_text_batch))
    with open(label_filename, "w", encoding="utf-8") as label_file:
        label_file.write("\n".join(label_text_batch))
    metrics = compute_metrics(hypothesis=pred_filename, references=[label_filename], no_skipthoughts=True, no_glove=True)
    # bleu = corpus_bleu([[label_text.split()] for label_text in label_text_batch], [pred_text.split() for pred_text in pred_text_batch])
    # rouge_types = ["rouge1", "rouge2", "rougeL"]
    # scorer = rouge_scorer.RougeScorer(rouge_types, use_stemmer=True)
    # rouge_scores: Dict[str, scoring.Score] = [scorer.score(label_text, pred_text) for label_text, pred_text in zip(label_text_batch, pred_text_batch)]
    # rouge_avg = {
    #     rouge_type: np.mean([score[rouge_type].fmeasure for score in rouge_scores])
    #     for rouge_type in rouge_types
    # }
    # return 0, f"Exact Match Accuracy: {accuracy:.3f}, BLEU-4: {metrics['Bleu_4']:.3f}, ROUGE-1: {rouge_avg['rouge1']:.3f}, ROUGE-2: {rouge_avg['rouge2']:.3f}, ROUGE-L: {rouge_avg['rougeL']:.3f}, METEOR: {metrics['METEOR']:.3f}"
    return 0, f"Exact Match Accuracy: {accuracy:.3f}, BLEU-4: {metrics['Bleu_4']:.3f}, ROUGE-L: {metrics['ROUGE_L']:.3f}, METEOR: {metrics['METEOR']:.3f}"

def evaluate_cls_task(model: MathGPTClassifier, dataset: Dataset, task: DownstreamTask, options: TrainOptions):
    # TODO: unit test
    all_predictions = []
    all_labels = []
    def accumulate_predictions(model_output, batch: CollatedBatch):
        predictions = torch.argmax(model_output[1], dim=-1)
        all_predictions.append(predictions.detach().cpu().numpy())
        all_labels.append(batch["cls_labels"].detach().cpu().numpy())

    loss = process_model_output(model, dataset, task, options, accumulate_predictions)

    all_preds_np = np.concatenate(all_predictions, axis=0)
    all_labels_np = np.concatenate(all_labels, axis=0)
    accuracy = metrics.accuracy_score(all_labels_np, all_preds_np)
    _, _, f1, _ = metrics.precision_recall_fscore_support(all_labels_np, all_preds_np)
    return loss, f"Accuracy: {accuracy:.3f}, F1: {f1:.3f}"
