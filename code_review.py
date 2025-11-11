import os
import sys
from dotenv import load_dotenv
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_mistralai.chat_models import ChatMistralAI
from langchain_community.retrievers import ArxivRetriever


# Load environment variables
load_dotenv()

# Load configuration from .env
CACHE_PATH = os.getenv("CACHE_PATH", "faiss_pdf_index")
DEFAULT_PDF_FOLDER = os.getenv("DEFAULT_PDF_FOLDER", "pdf_documents")


def load_api_key():
    apikey = os.getenv("MISTRAL_API_KEY")
    if not apikey:
        raise ValueError("MISTRAL_API_KEY not found in environment variables")
    return apikey


def initialize_llm(apikey):
    return ChatMistralAI(
        model="mistral-small-latest",
        api_key=apikey,
        temperature=0.2,
        max_retries=2,
    )


def get_pdf_files_from_folder(folder_path):
    """Get all PDF files from a specified folder"""
    pdf_files = []
    if not os.path.exists(folder_path):
        print(f"Folder {folder_path} does not exist. Creating it...")
        os.makedirs(folder_path)
        print(f"Please place your PDF files in the '{folder_path}' folder and run again.")
        return []
    
    for file_name in os.listdir(folder_path):
        if file_name.lower().endswith('.pdf'):
            full_path = os.path.join(folder_path, file_name)
            pdf_files.append(full_path)
    
    return pdf_files


def get_default_pdf_files():
    """Get default PDF files list from default_pdfs folder"""
    default_folder = "/app/default_pdfs"  # Путь внутри контейнера
    
    # Если файлы находятся в default_pdfs, используем их
    if os.path.exists(default_folder):
        pdf_files = []
        for file_name in os.listdir(default_folder):
            if file_name.lower().endswith('.pdf'):
                full_path = os.path.join(default_folder, file_name)
                pdf_files.append(full_path)
        if pdf_files:
            return pdf_files
    
    # Fallback: если папки нет, использовать старые пути
    return [
        "layout-parser-paper.pdf",
        "Python_vulnarabilities_1.pdf",
        "Python_vulnarabilities_2.pdf",
        "Python_vulnarabilities_detection.pdf",
        "Secure_vulnarabilities.pdf"
    ]



def load_pdfs_and_build_index(pdf_files, cache_suffix=""):
    """Load PDFs and build FAISS index with optional cache suffix"""
    all_docs = []
    loaded_files = []
    
    for file_path in pdf_files:
        if not os.path.exists(file_path):
            print(f"File {file_path} not found, skipping...")
            continue
        print(f"Loading documents from {file_path}")
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        all_docs.extend(docs)
        loaded_files.append(file_path)
    
    if not all_docs:
        raise ValueError("No PDF documents loaded")
    
    print(f"Loaded {len(loaded_files)} PDF files")
    
    splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    split_docs = []
    for doc in all_docs:
        split_docs.extend(splitter.split_documents([doc]))
    
    embedder = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    cache_path = CACHE_PATH + cache_suffix
    
    if os.path.exists(cache_path):
        print(f"Loading FAISS index from cache: {cache_path}")
        faiss_index = FAISS.load_local(cache_path, embedder, allow_dangerous_deserialization=True)
    else:
        print(f"Creating new FAISS index at: {cache_path}")
        faiss_index = FAISS.from_documents(split_docs, embedder)
        faiss_index.save_local(cache_path)
    
    return faiss_index.as_retriever(search_kwargs={"k": 5})

def analyze_code_with_rag(file_path, retriever, llm):
    with open(file_path, 'r', encoding='utf-8') as f:
        code_text = f.read()

    relevant_docs = retriever.invoke(code_text)

    if relevant_docs and len(relevant_docs) > 0:
        print("Relevant documents found, using RAG")
        context = "\n\n".join([doc.page_content for doc in relevant_docs])
        prompt = f"Based on the following context:\n\n{context}\n\nAnalyze the code:\n\n{code_text}"
        
        response = llm.invoke(prompt)
        answer = response.content
        sources = [doc.page_content for doc in relevant_docs]
    else:
        print("No relevant documents found, querying LLM directly")
        prompt = f"Analyze the following code:\n\n{code_text}"
        response = llm.invoke(prompt)
        answer = response.content
        sources = []

    return answer, sources


def analyze_code_without_rag(file_path, llm):
    with open(file_path, 'r', encoding='utf-8') as f:
        code_text = f.read()

    print("Analyzing code without RAG")
    prompt = f"Analyze the following code:\n\n{code_text}"
    response = llm.invoke(prompt)
    answer = response.content
    
    return answer, []


def save_output(answer, docs, output_path="output.txt", use_rag=True, source_type="default"):
    with open(output_path, "w", encoding="utf-8") as f:
        if use_rag:
            f.write(f"Answer (with RAG - source: {source_type}):\n")
        else:
            f.write("Answer (without RAG):\n")
        f.write(answer)
        if docs:
            f.write("\n\nUsed documents:\n")
            for i, doc in enumerate(docs, 1):
                f.write(f"\n--- Document {i} ---\n{doc[:500]}...\n")
        else:
            if use_rag:
                f.write("\n\nNo documents were used for RAG analysis.\n")


def main(input_file, use_rag=True, use_custom_pdf=False):
    apikey = load_api_key()
    llm = initialize_llm(apikey)
    
    if use_rag:
        if use_custom_pdf:
            print(f"Loading PDFs from '{DEFAULT_PDF_FOLDER}' folder...")
            pdf_files = get_pdf_files_from_folder(DEFAULT_PDF_FOLDER)
            if not pdf_files:
                print(f"No PDF files found in '{DEFAULT_PDF_FOLDER}'. Falling back to default PDFs.")
                pdf_files = get_default_pdf_files()
                source_type = "default"
            else:
                print(f"Found {len(pdf_files)} custom PDF files")
                source_type = "custom"
        else:
            pdf_files = get_default_pdf_files()
            source_type = "default"
        
        cache_suffix = "_custom" if use_custom_pdf else ""
        
        pdf_retriever = load_pdfs_and_build_index(pdf_files, cache_suffix=cache_suffix)
        answer, docs = analyze_code_with_rag(input_file, pdf_retriever, llm)
    else:
        answer, docs = analyze_code_without_rag(input_file, llm)
        source_type = "none"
    
    save_output(answer, docs, use_rag=use_rag, source_type=source_type)
    print("Analysis completed. Result saved to output.txt")


if __name__ == "__main__":
    use_rag = True
    use_custom_pdf = False
    input_file = None
    
    if len(sys.argv) < 2:
        print("Usage: python code_review.py <path_to_file.py> [--rag | --no-rag] [--custom-pdf | --default-pdf]")
        print("  --rag         : Use RAG with documents (default)")
        print("  --no-rag      : Use LLM without RAG")
        print("  --custom-pdf  : Use PDFs from folder specified in .env")
        print("  --default-pdf : Use built-in PDF list (default)")
        print(f"\nCurrent configuration:")
        print(f"  CACHE_PATH: {CACHE_PATH}")
        print(f"  DEFAULT_PDF_FOLDER: {DEFAULT_PDF_FOLDER}")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    for i in range(2, len(sys.argv)):
        flag = sys.argv[i]
        if flag == "--no-rag":
            use_rag = False
        elif flag == "--rag":
            use_rag = True
        elif flag == "--custom-pdf":
            use_custom_pdf = True
        elif flag == "--default-pdf":
            use_custom_pdf = False
        else:
            print(f"Unknown flag: {flag}")
            sys.exit(1)
    
    main(input_file, use_rag=use_rag, use_custom_pdf=use_custom_pdf)
