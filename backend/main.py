from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openai
import os
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.chat_models import ChatOpenAI

# Environment setup
openai.api_key = os.getenv("OPENAI_API_KEY")
CHROMA_PATH = "chroma"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
GPT_MODEL = "gpt-4o-mini"

# Initialize the components
def load_vector_store():
    emb_model = HuggingFaceEmbeddings(model_name=MODEL_NAME)
    return Chroma(persist_directory=CHROMA_PATH, embedding_function=emb_model)

def query_vector_store(db, query_text):
    results = db.similarity_search_with_relevance_scores(query_text, k=3)
    if len(results) == 0 or results[0][1] < 0.3:
        return "सम्बन्धित परिणाम भेटिएन।"
    return "\n\n---\n\n".join([doc.page_content for doc, _score in results])

def format_prompt(conversation_history, user_question, context_text, max_history=5):
    prompt_template = """
    तपाईं जुनु हुनुहुन्छ, सरकारी कार्यालयका प्रक्रियाहरू बुझ्न र कार्यहरू पूरा गर्न सहयोग पुर्‍याउन नेपाली नागरिकलाई सहयोग गर्ने ज्ञानयुक्त सहायक। प्रयोगकर्ताको प्रश्न र अघिल्लो कुराकानी इतिहासबाट सम्बन्धित विवरणहरू प्रयोग गरी सटीक, संक्षिप्त, र सहायक उत्तर दिनुहोस्। स्पष्टताका लागि अघिल्लो कुराकानीलाई स्पष्ट रूपमा उल्लेख गर्न आवश्यक नभएसम्म उल्लेख नगर्नुहोस्। डेटाबेसमा भएका तथ्यहरूका आधारमा मात्र उत्तर दिनुहोस्।

    ---

    **कुराकानीको इतिहास:**
    {conversation_history}

    **हालको प्रयोगकर्ताको प्रश्न:** 
    {user_question}

    **प्राप्त दस्तावेज डेटा:**
    {context}

    ---

    """
    trimmed_history = conversation_history[-max_history:]
    formatted_history = "\n".join([f"प्रयोगकर्ता: {entry['user']}\nसहायक: {entry['assistant']}" for entry in trimmed_history])
    return prompt_template.format(
        conversation_history=formatted_history,
        user_question=user_question,
        context=context_text
    )

# Initialize the model and vector store
model = ChatOpenAI(model=GPT_MODEL)
db = load_vector_store()

# Define Pydantic model for input and output
class UserInput(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str

# FastAPI app initialization
app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Store conversation history globally
conversation_history = []

# API endpoint to handle chat
@app.post("/chat", response_model=ChatResponse)
async def chat_with_bot(user_input: UserInput):
    global conversation_history

    user_question = user_input.question

    # Query the vector store for context
    context_text = query_vector_store(db, user_question)
    if not context_text:
        context_text = "सम्बन्धित डेटा उपलब्ध छैन।"

    # Format the prompt and generate response
    prompt = format_prompt(conversation_history, user_question, context_text)
    response = model.invoke(prompt).content

    # Append the conversation history
    conversation_history.append({"user": user_question, "assistant": response})

    return ChatResponse(answer=response)

# Run the FastAPI server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
