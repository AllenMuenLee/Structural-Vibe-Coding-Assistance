import os
from typing import List, Dict, Any, Optional

from tree_sitter_language_pack import get_parser
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_aws import BedrockEmbeddings

EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


def _detect_language(file_path: str) -> Optional[str]:
    """Detect language from file extension."""
    _, ext = os.path.splitext(file_path or "")
    return EXT_TO_LANG.get(ext.lower())


def _collect_subtrees(root, max_nodes: int = 2000):
    """Collect a bounded list of subtree nodes from the root."""
    subtrees = []
    stack = [root]
    while stack and len(subtrees) < max_nodes:
        node = stack.pop()
        subtrees.append(node)
        children = list(node.children)
        stack.extend(reversed(children))
    return subtrees


def _build_documents_from_ast(code: str, file_path: str, max_nodes: int = 2000, max_chunks: int = 200) -> List[Document]:
    """Build LangChain documents from AST subtrees."""
    language = _detect_language(file_path)
    if not language:
        return []
    parser = get_parser(language)
    source_bytes = code.encode("utf-8", errors="ignore")
    tree = parser.parse(source_bytes)

    subtrees = _collect_subtrees(tree.root_node, max_nodes=max_nodes)
    docs: List[Document] = []
    seen = set()

    for subtree in subtrees:
        text = code[subtree.start_byte:subtree.end_byte]
        if not text or text in seen:
            continue
        seen.add(text)
        metadata = {
            "file_path": os.path.normpath(file_path),
            "start_byte": subtree.start_byte,
            "end_byte": subtree.end_byte,
            "start_line": subtree.start_point[0] + 1,
            "end_line": subtree.end_point[0] + 1,
        }
        docs.append(Document(page_content=text, metadata=metadata))

    docs.sort(key=lambda d: len(d.page_content), reverse=True)
    if max_chunks and len(docs) > max_chunks:
        docs = docs[:max_chunks]
    return docs


class AstRagTable:
    """A lightweight RAG table for AST chunks using LangChain + FAISS."""

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        model_id = "amazon.titan-embed-text-v2:0",
        region_name: Optional[str] = None,
        credentials_profile_name: Optional[str] = None,
        model_parameters: Optional[Dict[str, Any]] = None,
    ):
        self.persist_dir = persist_dir
        self.embeddings = BedrockEmbeddings(
            model_id=model_id,
            region_name=os.getenv("AWS_REGION"),
            credentials_profile_name=credentials_profile_name,
            model_kwargs=model_parameters or {},
        )
        self.vectorstore: Optional[FAISS] = None

    def add_code(self, code: str, file_path: str, max_nodes: int = 2000, max_chunks: int = 200):
        """Add AST chunks from a code string into the RAG table."""
        docs = _build_documents_from_ast(code, file_path, max_nodes=max_nodes, max_chunks=max_chunks)
        self.add_documents(docs)

    def add_file(self, file_path: str, max_nodes: int = 2000, max_chunks: int = 200):
        """Read a file and add its AST chunks into the RAG table."""
        if not os.path.exists(file_path):
            return
        with open(file_path, "r", encoding="utf-8") as fh:
            code = fh.read()
        self.add_code(code, file_path, max_nodes=max_nodes, max_chunks=max_chunks)

    def add_documents(self, docs: List[Document]):
        """Add documents to the RAG table."""
        if not docs:
            return
        if self.vectorstore is None:
            self.vectorstore = FAISS.from_documents(docs, self.embeddings)
        else:
            self.vectorstore.add_documents(docs)

    def save(self):
        """Persist the vector store to disk."""
        if self.persist_dir and self.vectorstore is not None:
            os.makedirs(self.persist_dir, exist_ok=True)
            self.vectorstore.save_local(self.persist_dir)

    def load(self):
        """Load the vector store from disk."""
        if self.persist_dir and os.path.isdir(self.persist_dir):
            self.vectorstore = FAISS.load_local(self.persist_dir, self.embeddings, allow_dangerous_deserialization=True)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search the RAG table and return ranked matches."""
        if not query or self.vectorstore is None:
            return []
        results = self.vectorstore.similarity_search_with_score(query, k=top_k)
        matches = []
        for doc, score in results:
            matches.append({
                "text": doc.page_content,
                "score": float(score),
                "metadata": doc.metadata,
            })
        return matches


def search_ast_chunks(code: str, file_path: str, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search AST chunks for a single file using an in-memory RAG table."""
    table = AstRagTable(persist_dir=None)
    table.add_code(code, file_path)
    return table.search(query_text, top_k=top_k)
