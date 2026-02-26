import os
import torch
from transformers import AutoModel, AutoTokenizer
from tree_sitter_language_pack import get_parser

EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


def _detect_language(file_path):
    _, ext = os.path.splitext(file_path)
    return EXT_TO_LANG.get(ext.lower())


_EMBED_TOKENIZER = None
_EMBED_MODEL = None
_EMBED_DEVICE = None


def _get_embed_model():
    global _EMBED_TOKENIZER, _EMBED_MODEL, _EMBED_DEVICE
    if _EMBED_TOKENIZER is not None and _EMBED_MODEL is not None and _EMBED_DEVICE is not None:
        return _EMBED_TOKENIZER, _EMBED_MODEL, _EMBED_DEVICE

    _EMBED_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _EMBED_TOKENIZER = AutoTokenizer.from_pretrained(
        "Salesforce/codet5p-110m-embedding",
        trust_remote_code=True
    )
    _EMBED_MODEL = AutoModel.from_pretrained(
        "Salesforce/codet5p-110m-embedding",
        trust_remote_code=True,
        torch_dtype=torch.float16 if _EMBED_DEVICE.type == "cuda" else torch.float32,
        device_map={"": 0} if _EMBED_DEVICE.type == "cuda" else None
    )
    _EMBED_MODEL.config.model_type = "t5"
    try:
        _EMBED_MODEL = _EMBED_MODEL.to_bettertransformer()
    except Exception:
        pass
    _EMBED_MODEL.eval()
    if _EMBED_DEVICE.type != "cuda":
        _EMBED_MODEL = _EMBED_MODEL.to(_EMBED_DEVICE)
    return _EMBED_TOKENIZER, _EMBED_MODEL, _EMBED_DEVICE


def _collect_subtrees(root, max_nodes=2000):
    subtrees = []
    stack = [root]
    while stack and len(subtrees) < max_nodes:
        node = stack.pop()
        subtrees.append(node)
        children = list(node.children)
        stack.extend(reversed(children))
    return subtrees


def _get_embedding(texts, max_length=2048):
    tokenizer, model, device = _get_embed_model()
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        max_length=max_length,
        padding="max_length",
        truncation=True
    ).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
        return outputs.cpu().detach()


def get_ast_embeddings(code, file_path, max_nodes=2000, max_chunks=200):
    language = _detect_language(file_path)
    if not language:
        return {"chunks": []}
    parser = get_parser(language)
    source_bytes = code.encode("utf-8", errors="ignore")
    tree = parser.parse(source_bytes)

    subtrees = _collect_subtrees(tree.root_node, max_nodes=max_nodes)
    src_texts = []
    for subtree in subtrees:
        text = code[subtree.start_byte:subtree.end_byte]
        if text and text not in src_texts:
            src_texts.append(text)

    if not src_texts:
        return {"chunks": []}

    embeddings = _get_embedding(src_texts)
    chunks = []
    for i, src_text in enumerate(src_texts):
        emb = embeddings[i]
        chunks.append({
            "text": src_text,
            "embedding": emb.squeeze().tolist()
        })

    chunks.sort(key=lambda c: len(c["text"]), reverse=True)
    if max_chunks and len(chunks) > max_chunks:
        chunks = chunks[:max_chunks]
    return {"chunks": chunks}
