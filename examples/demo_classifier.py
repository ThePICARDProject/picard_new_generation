#!/usr/bin/env python3
"""
Demo classification algorithm conforming to PICARD spark-classification-v1 protocol.
Used for local testing and benchmarking verification without requiring a Spark cluster.
"""

import os
import sys
import time

def main():
    if len(sys.argv) < 4:
        print("Usage: demo_classifier.py <dataset_path> <result_dir> <result_name> [hyperparameters...]")
        sys.exit(1)

    dataset_path = sys.argv[1]
    result_dir = sys.argv[2]
    result_name = sys.argv[3]
    hyperparameters = sys.argv[4:]

    print("=" * 60)
    print("DEMO CLASSIFIER (spark-classification-v1)")
    print(f"Dataset:         {dataset_path}")
    print(f"Output Target:   {os.path.join(result_dir, result_name)}")
    print(f"Hyperparameters: {' '.join(hyperparameters)}")
    print("=" * 60)

    # Parse arguments if matching SupervisedMLRF:
    # numClasses, numTrees, impurity, maxDepth, maxBins, percentLabeled
    num_trees = int(hyperparameters[1]) if len(hyperparameters) > 1 and hyperparameters[1].isdigit() else 10
    impurity = hyperparameters[2] if len(hyperparameters) > 2 else "gini"
    max_depth = int(hyperparameters[3]) if len(hyperparameters) > 3 and hyperparameters[3].isdigit() else 5

    # Simulate model training with small delay
    start_time = time.time()
    time.sleep(0.05 + 0.01 * min(num_trees, 50))

    # Calculate synthetic metrics based on hyperparameters
    base_acc = 0.82
    tree_bonus = min(0.08, num_trees * 0.002)
    depth_bonus = min(0.05, max_depth * 0.005)
    impurity_bonus = 0.015 if impurity.lower() == "gini" else 0.010

    accuracy = round(min(0.985, base_acc + tree_bonus + depth_bonus + impurity_bonus), 4)
    precision = round(accuracy * 0.988, 4)
    recall = round(accuracy * 0.992, 4)
    f1_score = round(2 * (precision * recall) / (precision + recall), 4)
    elapsed_time = round(time.time() - start_time, 3)

    print("\n--- Training & Evaluation Log ---")
    print(f"Loaded dataset from: {dataset_path}")
    print(f"Random Forest built with {num_trees} trees, maxDepth={max_depth}, impurity={impurity}")
    print(f"Accuracy = {accuracy}")
    print(f"Precision = {precision}")
    print(f"Recall: {recall}")
    print(f"F1-score: {f1_score}")
    print(f"Time taken: {elapsed_time}s")

    # Create destination output directory and write part-00000 file
    target_dir = os.path.join(result_dir, result_name)
    os.makedirs(target_dir, exist_ok=True)
    part_file = os.path.join(target_dir, "part-00000")

    with open(part_file, "w", encoding="utf-8") as f:
        f.write("=== Model Evaluation Report ===\n")
        f.write(f"Accuracy: {accuracy}\n")
        f.write(f"Precision: {precision}\n")
        f.write(f"Recall: {recall}\n")
        f.write(f"F1-Score: {f1_score}\n")
        f.write(f"Trees: {num_trees}\n")
        f.write(f"Impurity: {impurity}\n")
        f.write(f"MaxDepth: {max_depth}\n")
        f.write(f"ExecutionTime_s: {elapsed_time}\n")

    print(f"\n[SUCCESS] Results written to {part_file}")

if __name__ == "__main__":
    main()
