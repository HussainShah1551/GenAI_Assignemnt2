from langchain_core.vectorstores import InMemoryVectorStore
from langchain_fireworks import FireworksEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter   
from langchain.document_loaders import PyPDFLoader
from langsmith import traceable
from langchain_fireworks import ChatFireworks
import requests
import os
import json
from langchain_core.prompts import PromptTemplate
from langchain.evaluation import load_evaluator


#The program prompts the user to ask a question , after which the program will generate an answer based on the question asked by the user using documents 
#The program will then validate the response generated by the chatbot using validation  and provide a score out of 10 for each criterion and give feedback for improvement. 
# The program will then evaluate the response based on conciseness, accuracy, and relevance of the response based on the context.
# The program will then provide the evaluation result based on the context.


# Langsmith tracing
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"] = "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"
os.environ["LANGCHAIN_PROJECT"] = "pr-wooden-trinket-46"

#Loading Loan policy document using PyPDFLoader
loan_policy = PyPDFLoader("/Users/emumba/Desktop/Personal/Langchain/Loan Application.pdf")
content = loan_policy.load()


#splitting the document into chunks
splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20)
splitted_docs = splitter.split_documents(content)

embeddings = FireworksEmbeddings(api_key="fw_3ZTz64NwEr4zGhqt1neQyn7w")

# Create a vector store from the splitted documents
vectorstore = InMemoryVectorStore.from_documents(
    documents=splitted_docs,
    embedding=embeddings,
)
# Create a retriever from the vector store
retriever = vectorstore.as_retriever(k=10)



# Define LLM model
llm_model = ChatFireworks(
    model="accounts/fireworks/models/mixtral-8x7b-instruct",
    base_url="https://api.fireworks.ai/inference/v1/completions",
    api_key="fw_3ZTz64NwEr4zGhqt1neQyn7w",
    temperature=0.1,
)

#Fireworks API to send custom format messages
def call_fireworks_api(messages, api_key):
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    payload = {
        "model": "accounts/fireworks/models/mixtral-8x7b-instruct",
        "max_tokens": 8192,
        "top_p": 1,
        "top_k": 40,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "temperature": 0.1,
        "messages": messages,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code != 200:
        raise Exception(f"Fireworks API error: {response.text}")
    return response.json()

@traceable()
def rag_bot_with_chatprompt(question: str) -> dict:
    docs = retriever.invoke(question)
    
    if not docs:
        return {"answer": "No relevant documents found.", "documents": []}
    
    docs_string = "\n".join(doc.page_content for doc in docs)
    
    PromptTemplate = {
        "template": """
        SYSTEM: You are a helpful assistant skilled at analyzing source information and answering questions concisely.
        Use the following source documents to answer the user's question. If you don't know the answer, just say you don't know.
        
        DOCUMENTS:
        {documents}
        
        USER: {question}
        """,
        "variables": {
            "documents": docs_string,
            "question": question
        }
    }
    
    filled_prompt = PromptTemplate["template"].format(**PromptTemplate["variables"])
    
    messages = [
        {"role": "system", "content": filled_prompt},
        {"role": "user", "content": question},
    ]
    
    try:
        response = call_fireworks_api(messages=messages, api_key="fw_3ZTz64NwEr4zGhqt1neQyn7w")
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No response")
    except Exception as e:
        answer = f"Error: {str(e)}"
    
    return {"answer": answer, "documents": docs}





user_question = input("Please ask your question relating to Emumba policy: ")



question = user_question

response = rag_bot_with_chatprompt(question)

answer = response["answer"]
documents = response["documents"]
print("\n\nAnswer",answer)




# Define a prompt template for validation prompt 
validation_prompt = PromptTemplate(
    input_variables=["query", "response", "context"],
    template="""
    Given the user query: "{query}",
    the response generated by the chatbot: "{response}",
    and the context retrieved from the database: "{context}",
    please validate the response based on:
    1. Accuracy: Does the response accurately answer the query?
    2. Relevance: Is the response relevant to the retrieved context?
    3. Completeness: Does the response fully address the query?
    Provide a score out of 10 for each criterion and give feedback for improvement.
    """
)
@traceable()
def validate_response(query: str, response: str, context: str) -> dict:
    filled_prompt = validation_prompt.format(query=query, response=response, context=context)
    
    messages = [
        {"role": "system", "content": "You are an AI validator tasked with evaluating chatbot responses."},
        {"role": "user", "content": filled_prompt},
    ]
    
    try:
        validation_response = call_fireworks_api(messages=messages, api_key="fw_3ZTz64NwEr4zGhqt1neQyn7w")
        evaluation = validation_response.get("choices", [{}])[0].get("message", {}).get("content", "No validation result")
    except Exception as e:
        evaluation = f"Error: {str(e)}"
    
    return {"evaluation": evaluation}

query = question,
response=answer,
context=documents


validation_result = validate_response(query=query, response=response, context=context)

print("\n\nPrompt Template Validation:\n")
print(validation_result["evaluation"])



@traceable()
# Define a prompt template for langchain Evaluator 
def langchain_evaluator(query: str, response: str, context: str, api_key: str) -> dict:
    messages = [
        {"role": "system", "content": "You are an AI validator tasked with evaluating chatbot responses."},
        {"role": "user", "content": f"Given the user query: '{query}', and the response: '{response}', evaluate the conciseness accuracy and  relevance of the response based on the context."}
    ]
    
    try:
        validation_response = call_fireworks_api(messages=messages, api_key=api_key)
        evaluation = validation_response.get("choices", [{}])[0].get("message", {}).get("content", "No validation result")
    except Exception as e:
        evaluation = f"Error: {str(e)}"
    
    return {"evaluation": evaluation}

query = question
response = answer
context = documents
api_key = "fw_3ZTz64NwEr4zGhqt1neQyn7w" 

evaluation_result = langchain_evaluator(query, response, context, api_key)
print("\n\nLangchain Evaluator Evaluation result\n\n",evaluation_result["evaluation"])