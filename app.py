from flask import Flask, request, jsonify
from google import genai
from google.genai import types
import os
import json
import textwrap
from dotenv import load_dotenv
from flask_cors import CORS

# load_dotenv("apikeyss.env") # Make sure your environment loads the key

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)

# --- Default/Initial States ---
user_language = "English"
user_personality = "Study Buddy"
WELCOME_MESSAGE_TEXT = "Hello! I’m your Personal AI Assistant. How can I help you today?"

# --- Personality-based Instruction Mapping ---
PERSONALITY_INSTRUCTIONS = {
    'Study Buddy': "You are a professional and concise academic tutor. Your tone should be educational, encouraging, and focused on structured learning. Prioritize explaining concepts clearly and giving practical study tips.",
    'Wellness Coach': "You are an empathetic, gentle, and motivational life coach. Your tone should be supportive, focusing on mental health, goal setting, and positive reinforcement. Use an uplifting and warm style.",
    'Career Advisor': "You are a pragmatic, formal, and insightful career counselor. Your tone should be professional, advisory, and provide actionable, strategic advice for career development and planning.",
}

# --- Build System Prompt with Personality ---
def build_system_prompt(language, personality):
    instruction = PERSONALITY_INSTRUCTIONS.get(personality, PERSONALITY_INSTRUCTIONS['Study Buddy'])
    return textwrap.dedent(f"""
    {instruction}

    Your core identity is a friendly, concise, and professional AI assistant.
    You must always reply in **{language} language only**.

    --- CORE RULES ---
    1. Use natural and fluent {language}.
    2. Keep responses short and to the point, suitable for a mobile chat.
    3. Do not mix other languages.
    4. When giving choices, include them in this exact format:
       <<OPTION:Option 1>>
       <<OPTION:Option 2>>
       ...
    5. The user's prompt will contain the current personality mode. Ignore it in your visible response but follow its instructions.
    """)

# --- Initialize Gemini ---
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY environment variable not found. Chatbot will fail.")
        client = None
    else:
        client = genai.Client(api_key=api_key)
        print("✅ Gemini client initialized successfully.")
except Exception as e:
    print(f"❌ Gemini initialization error: {e}")
    client = None

# --- Global conversation history ---
conversation_history = []

# --- Reset conversation ---
def reset_conversation(language, personality):
    global conversation_history
    conversation_history = []
    welcome_translated = f"Hello! I’m your Personal AI Assistant, currently set as a **{personality}**. How can I help you today?"
    conversation_history.append(types.Content(role="model", parts=[types.Part(text=welcome_translated)]))

# --- Get Gemini response ---
def get_gemini_response(history, user_input, language, personality):
    global client
    if client is None:
        return "🤖 Error: Gemini client not initialized. Check server logs."

    try:
        system_prompt = build_system_prompt(language, personality)
        contents = [
            types.Content(role="user", parts=[types.Part(text=system_prompt)]),
            *history,
            types.Content(role="user", parts=[types.Part(text=user_input)])
        ]

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.5)
        )

        history.append(types.Content(role="user", parts=[types.Part(text=user_input)]))
        history.append(response.candidates[0].content)

        return response.text.strip()
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return "🤖 Error: Could not contact Gemini model."

# --- Initialize on startup ---
reset_conversation(user_language, user_personality)

# --- Chat endpoint ---
@app.route('/chatbot', methods=['POST'])
def get_chat_response():
    global conversation_history, user_language, user_personality

    data = request.get_json()
    user_input = data.get('user_input', '').strip()
    selected_language = data.get('language', user_language)
    selected_personality = data.get('personality', user_personality)

    user_input_lower = user_input.lower()
    is_state_change = (selected_language != user_language) or (selected_personality != user_personality)

    if is_state_change:
        user_language = selected_language
        user_personality = selected_personality
        reset_conversation(user_language, user_personality)

        initial_message = (
            f"Hello! I've set my language to **{user_language}** "
            f"and I'm now your **{user_personality}**."
        )

        return jsonify({
            'response': initial_message,
            'language': user_language,
            'personality': user_personality
        })

    if any(k in user_input_lower for k in ["reset", "cancel", "stop", "start over", "auto_reset_scroll"]):
        reset_conversation(user_language, user_personality)

        if user_input_lower == "auto_reset_scroll":
            return jsonify({'response': '...', 'silent': True})

        return jsonify({
            'response': f"🔄 Conversation reset. I'm now your **{user_personality}** in **{user_language}**.",
            'language': user_language
        })

    bot_response = get_gemini_response(conversation_history, user_input, user_language, user_personality)
    return jsonify({
        'response': bot_response,
        'language': user_language,
        'personality': user_personality
    })

# --- Status + root endpoints ---
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'GET':
        return jsonify({
            "status": "✅ Server is running successfully!",
            "message": "Welcome to Personal AI Chatbot API",
            "endpoints": {
                "POST": "/chatbot"
            }
        })
    
    if request.method == 'POST':
        return jsonify({
            "status": "POST request received successfully!",
            "message": "Backend root POST working. Use /chatbot for AI chat."
        })

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'status': '✅ Server is running',
        'model': 'Gemini 2.5 Flash',
        'language': user_language,
        'personality': user_personality
    }), 200

# --- Run app ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
