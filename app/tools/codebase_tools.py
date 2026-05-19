"""Codebase indexing and search tools using ChromaDB."""
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from app.tools.base import BaseTool, ToolSchema, ToolParameter

# ChromaDB path (same as long_term.py)
CHROMA_DB_PATH = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data" / "chroma"

logger = logging.getLogger(__name__)

# Supported file extensions
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.md', 
    '.html', '.css', '.scss', '.less', '.vue', '.svelte'
}

# Directories to skip during indexing.
EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".recycle",
    "data",
    "logs",
    "workspace"
}

# Chunk size in lines
CHUNK_SIZE = 50

# Codebase collection name (separate from memory)
CODEBASE_COLLECTION = "codebase_index"


def get_codebase_collection():
    """Get or create the codebase ChromaDB collection."""
    # Keep client initialization consistent with app.memory.long_term
    # to avoid "existing instance with different settings" conflicts.
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    
    # Get or create collection
    try:
        collection = client.get_collection(name=CODEBASE_COLLECTION)
        logger.info(f"Using existing codebase collection: {CODEBASE_COLLECTION}")
    except:
        collection = client.create_collection(
            name=CODEBASE_COLLECTION,
            metadata={"description": "Codebase indexing for semantic search"}
        )
        logger.info(f"Created new codebase collection: {CODEBASE_COLLECTION}")
    
    return collection


def chunk_code(content: str, chunk_size: int = CHUNK_SIZE) -> List[Dict[str, Any]]:
    """Split code content into chunks with metadata.
    
    Returns list of dicts with:
    - content: the code chunk
    - start_line: starting line number
    - end_line: ending line number
    """
    lines = content.split('\n')
    chunks = []
    
    for i in range(0, len(lines), chunk_size):
        chunk_lines = lines[i:i + chunk_size]
        chunk_content = '\n'.join(chunk_lines)
        
        # Skip empty chunks
        if not chunk_content.strip():
            continue
            
        chunks.append({
            'content': chunk_content,
            'start_line': i + 1,
            'end_line': min(i + chunk_size, len(lines))
        })
    
    return chunks


def get_file_language(file_path: str) -> str:
    """Determine programming language from file extension."""
    ext = Path(file_path).suffix.lower()
    
    language_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'jsx',
        '.tsx': 'tsx',
        '.json': 'json',
        '.md': 'markdown',
        '.html': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.less': 'less',
        '.vue': 'vue',
        '.svelte': 'svelte'
    }
    
    return language_map.get(ext, 'unknown')


class IndexCodebaseTool(BaseTool):
    """Index a codebase directory into ChromaDB for semantic search."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="index_codebase",
            description="Index all code files in a directory into ChromaDB for semantic search. Supports Python, JavaScript, TypeScript, React, and more.",
            parameters=[
                ToolParameter(
                    name="directory",
                    type="string",
                    description="Root directory to index (default: workspace)",
                    required=False
                ),
                ToolParameter(
                    name="extensions",
                    type="string",
                    description="Comma-separated file extensions to index (default: .py,.js,.ts,.jsx,.tsx,.json,.md,.html,.css,.scss)",
                    required=False
                ),
                ToolParameter(
                    name="chunk_size",
                    type="integer",
                    description="Lines per chunk (default: 50)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, directory: str = None, extensions: str = None, chunk_size: int = CHUNK_SIZE, **kwargs) -> str:
        try:
            # Use current project root as default.
            if not directory:
                directory = str(Path(os.getcwd()))
            
            directory_path = Path(directory).resolve()
            
            if not directory_path.exists():
                return f"Error: Directory not found: {directory}"
            
            # Parse extensions
            if extensions:
                ext_set = set(ext.strip() for ext in extensions.split(','))
            else:
                ext_set = CODE_EXTENSIONS
            
            # Get codebase collection
            collection = get_codebase_collection()
            
            # Track stats
            files_indexed = 0
            chunks_added = 0
            errors = []
            
            # Walk directory and index files
            for file_path in directory_path.rglob('*'):
                if any(part in EXCLUDED_DIR_NAMES for part in file_path.parts):
                    continue
                if file_path.is_file() and file_path.suffix.lower() in ext_set:
                    try:
                        # Skip very large files (> 1MB)
                        if file_path.stat().st_size > 1_000_000:
                            logger.warning(f"Skipping large file: {file_path}")
                            continue
                        
                        # Read file
                        try:
                            content = file_path.read_text(encoding='utf-8', errors='ignore')
                        except Exception as e:
                            errors.append(f"Could not read {file_path}: {e}")
                            continue
                        
                        # Skip empty files
                        if not content.strip():
                            continue
                        
                        # Chunk the code
                        chunks = chunk_code(content, chunk_size)
                        
                        if not chunks:
                            continue
                        
                        # Get relative path for cleaner IDs
                        try:
                            rel_path = file_path.relative_to(directory_path)
                        except:
                            rel_path = file_path.name
                        
                        language = get_file_language(str(file_path))
                        
                        # Add chunks to collection
                        for idx, chunk in enumerate(chunks):
                            chunk_id = f"{rel_path}_{idx}"
                            
                            collection.add(
                                documents=[chunk['content']],
                                metadatas=[{
                                    'filename': str(rel_path),
                                    'filepath': str(file_path),
                                    'language': language,
                                    'start_line': chunk['start_line'],
                                    'end_line': chunk['end_line'],
                                    'chunk_index': idx,
                                    'total_chunks': len(chunks)
                                }],
                                ids=[chunk_id]
                            )
                            chunks_added += 1
                        
                        files_indexed += 1
                        
                        if files_indexed % 10 == 0:
                            logger.info(f"Indexed {files_indexed} files, {chunks_added} chunks so far...")
                        
                    except Exception as e:
                        errors.append(f"Error indexing {file_path}: {e}")
                        logger.error(f"Error indexing {file_path}: {e}")
            
            result = f"✅ Codebase indexing complete!\n\n"
            result += f"📁 Directory: {directory_path}\n"
            result += f"📄 Files indexed: {files_indexed}\n"
            result += f"🧩 Total chunks: {chunks_added}\n"
            result += f"🔤 Extensions: {', '.join(ext_set)}\n"
            
            if errors:
                result += f"\n⚠️  Errors ({len(errors)}):\n"
                for error in errors[:5]:  # Show first 5 errors
                    result += f"  - {error}\n"
                if len(errors) > 5:
                    result += f"  ... and {len(errors) - 5} more\n"
            
            logger.info(f"Indexed {files_indexed} files with {chunks_added} chunks")
            return result
            
        except Exception as e:
            logger.error(f"Failed to index codebase: {str(e)}", exc_info=True)
            return f"Error indexing codebase: {str(e)}"


class SearchCodebaseTool(BaseTool):
    """Search the indexed codebase using semantic search."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="search_codebase",
            description="Search the indexed codebase using semantic search. Returns relevant code chunks with file paths and line numbers.",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query (e.g., 'authentication logic', 'database connection', 'API routes')",
                    required=True
                ),
                ToolParameter(
                    name="n_results",
                    type="integer",
                    description="Number of results to return (default: 5)",
                    required=False
                ),
                ToolParameter(
                    name="language",
                    type="string",
                    description="Filter by language (e.g., 'python', 'javascript', 'typescript')",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, query: str, n_results: int = 5, language: str = None, **kwargs) -> str:
        try:
            collection = get_codebase_collection()
            
            # Check if collection has any data
            count = collection.count()
            if count == 0:
                return "❌ No codebase indexed yet. Run 'index_codebase' first to index your project."
            
            # Build filter if language specified
            where_filter = {"language": language} if language else None
            
            # Query collection
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter
            )
            
            if not results['documents'][0]:
                return f"🔍 No results found for: '{query}'"
            
            # Format results
            output = f"🔍 Search results for: '{query}'\n"
            output += f"📊 Found {len(results['documents'][0])} relevant chunks\n\n"
            output += "=" * 60 + "\n\n"
            
            for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            )):
                relevance = max(0, min(100, int((1 - distance) * 100)))
                
                output += f"📄 **{metadata['filename']}** (lines {metadata['start_line']}-{metadata['end_line']})\n"
                output += f"   Language: {metadata['language']} | Relevance: {relevance}%\n"
                output += f"   Path: {metadata['filepath']}\n"
                output += f"```\n{doc[:500]}...\n```\n\n"
            
            logger.info(f"Codebase search for '{query}' returned {len(results['documents'][0])} results")
            return output
            
        except Exception as e:
            logger.error(f"Failed to search codebase: {str(e)}", exc_info=True)
            return f"Error searching codebase: {str(e)}"


class GetFileSummaryTool(BaseTool):
    """Get a summary of what a specific file does using DeepSeek."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_file_summary",
            description="Ask DeepSeek to analyze and summarize what a specific file does. Useful for understanding code files quickly.",
            parameters=[
                ToolParameter(
                    name="filepath",
                    type="string",
                    description="Path to the file to summarize",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, filepath: str, **kwargs) -> str:
        try:
            file_path = Path(filepath).resolve()
            
            if not file_path.exists():
                return f"❌ File not found: {filepath}"
            
            # Read file
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception as e:
                return f"❌ Error reading file: {e}"
            
            # Limit content length
            max_length = 4000
            if len(content) > max_length:
                content = content[:max_length] + "\n... [truncated]"
            
            # Build prompt for DeepSeek
            language = get_file_language(str(file_path))
            
            prompt = f"""Analyze this {language} file and provide a summary:

**File:** {file_path.name}
**Path:** {file_path}

**Code:**
```{language}
{content}
```

Please provide:
1. **Purpose**: What does this file do?
2. **Key Functions/Classes**: Main components
3. **Dependencies**: What does it import/use?
4. **Summary**: Brief explanation in 2-3 sentences

Keep it concise but informative."""

            # Get summary from LLM
            from app.config import DEFAULT_MODEL
            from app.llm.ollama import chat_with_ollama
            
            messages = [{"role": "user", "content": prompt}]
            
            system_prompt = "You are a code analysis expert. Provide clear, concise summaries of code files."
            
            summary = chat_with_ollama(messages, model=DEFAULT_MODEL, system_prompt=system_prompt)
            
            if summary.startswith("Error:"):
                return f"❌ Failed to get summary: {summary}"
            
            result = f"📄 **File Analysis: {file_path.name}**\n"
            result += f"📍 Path: {file_path}\n"
            result += f"🔤 Language: {language}\n"
            result += f"📏 Size: {file_path.stat().st_size} bytes\n\n"
            result += "=" * 60 + "\n\n"
            result += summary
            
            logger.info(f"Generated summary for {file_path}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get file summary: {str(e)}", exc_info=True)
            return f"Error getting file summary: {str(e)}"
