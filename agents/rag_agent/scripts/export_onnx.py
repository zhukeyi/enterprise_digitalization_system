"""Export BGE embedding model to ONNX with INT8 dynamic quantization.

P4 T2a: Converts a sentence-transformers model (e.g. BGE-small-zh-v1.5) into an
ONNX graph with INT8 quantized weights (~100 MB vs ~400 MB PyTorch, 4x smaller).

Usage::

    python agents/rag_agent/scripts/export_onnx.py \
        --model BAAI/bge-small-zh-v1.5 \
        --output ~/.cache/fde/bge_small_int8.onnx \
        [--no-quantize]

The ONNX file contains just the transformer forward pass (token embeddings →
last_hidden_state). Pooling and L2 normalization are done in Python at
inference time (fast, no ONNX complexity).

Output artifacts:
    <output>.onnx          — FP32 ONNX (if --no-quantize)
    <output>_int8.onnx     — INT8 quantized ONNX
    <output>_config.json   — dimension, max_seq_len, pooling, model name
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import torch


def _get_transformer(model):
    """Extract the underlying transformer (e.g. BertModel) from a SentenceTransformer."""
    # SentenceTransformer >= 3.0 has model[...].auto_model
    # Try multiple paths for robustness
    try:
        # st >= 3: model[0].auto_model
        return model[0].auto_model
    except (AttributeError, IndexError, TypeError):
        pass
    try:
        # st >= 2: _modules["0"].auto_model
        return model._modules["0"].auto_model
    except (AttributeError, KeyError):
        pass
    try:
        # _first_module() accessor
        return model._first_module().auto_model
    except (AttributeError, Exception):
        raise RuntimeError(
            "Could not extract transformer from SentenceTransformer model. "
            "Please check the model structure."
        )


def export_onnx(model_name: str, output_path: str, quantize: bool = True) -> dict:
    """Export a sentence-transformers model to ONNX, optionally INT8 quantized.

    Returns a dict with metadata (dimension, paths, sizes).
    """
    from sentence_transformers import SentenceTransformer

    print(f"Loading model: {model_name}")
    st_model = SentenceTransformer(model_name, device="cpu")

    # Extract config
    dim = st_model.get_sentence_embedding_dimension() or 768
    max_seq_length = getattr(st_model, "max_seq_length", 512) or 512
    tokenizer_name = str(st_model.tokenizer.name_or_path) if st_model.tokenizer else model_name
    print(f"  Dimension: {dim}, Max seq len: {max_seq_length}")

    # Get transformer
    transformer = _get_transformer(st_model)
    transformer.eval()

    # Create dummy inputs
    dummy = st_model.tokenizer(
        ["test sentence for export"],
        padding="max_length",
        truncation=True,
        max_length=max_seq_length,
        return_tensors="pt",
    )

    input_ids = dummy["input_ids"]
    attention_mask = dummy["attention_mask"]

    # Export to ONNX
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fp32_path = out_path
    if quantize:
        fp32_path = out_path.with_suffix(".fp32.onnx")

    print(f"Exporting ONNX (FP32) to: {fp32_path}")
    t0 = time.monotonic()

    torch.onnx.export(
        transformer,
        (input_ids, attention_mask),
        str(fp32_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
        },
        opset_version=14,
        do_constant_folding=True,
    )
    print(f"  FP32 exported in {time.monotonic() - t0:.1f}s ({_size_mb(fp32_path):.1f} MB)")

    # INT8 quantization
    int8_path = out_path
    if quantize:
        print(f"Quantizing INT8 to: {int8_path}")
        t0 = time.monotonic()
        from onnxruntime.quantization import QuantType, quantize_dynamic

        quantize_dynamic(
            str(fp32_path),
            str(int8_path),
            weight_type=QuantType.QInt8,
            extra_options={"ActivationSymmetric": True},
        )
        print(f"  INT8 quantized in {time.monotonic() - t0:.1f}s ({_size_mb(int8_path):.1f} MB)")

    # Write config
    config_path = out_path.with_suffix(".config.json")
    config = {
        "model_name": model_name,
        "tokenizer_name": tokenizer_name,
        "dimension": dim,
        "max_seq_length": max_seq_length,
        "quantized": quantize,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    config_path.write_text(json.dumps(config, indent=2))
    print(f"Config: {config_path}")

    return config


def _size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def main():
    parser = argparse.ArgumentParser(description="Export BGE model to ONNX")
    parser.add_argument(
        "--model",
        default=os.getenv("FDE_RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        help="HuggingFace model name",
    )
    parser.add_argument(
        "--output",
        default=os.path.expanduser("~/.cache/fde/bge_model_int8.onnx"),
        help="Output .onnx file path",
    )
    parser.add_argument(
        "--no-quantize",
        action="store_true",
        help="Skip INT8 quantization (keep FP32)",
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=None,
        help="Override max sequence length (default: model default)",
    )
    args = parser.parse_args()

    config = export_onnx(args.model, args.output, quantize=not args.no_quantize)

    # Summary
    out_path = Path(args.output)
    final_onnx = out_path
    print(f"\nDone. Model: {config['model_name']}, dim={config['dimension']}")
    print(f"  ONNX: {final_onnx} ({_size_mb(final_onnx):.1f} MB)")
    print(f"  Config: {out_path.with_suffix('.config.json')}")
    print(f"\nTo use: set FDE_EMBEDDING_BACKEND=onnx FDE_ONNX_MODEL_PATH={final_onnx}")


if __name__ == "__main__":
    main()
