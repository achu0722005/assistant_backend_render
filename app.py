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

    Example:
    User: Tell me about health check-ups (Current Personality: Wellness Coach. Respond in English)
    Assistant:
    That's a great step towards self-care! Health check-ups are key to staying on track.
    <<OPTION:General Importance>>
    <<OPTION:Finding the Right Doctor>>
    <<OPTION:Staying Motivated>>
    """)

# --- Initialize Gemini ---
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        # Fallback to a placeholder if the key isn't set, so the app still runs
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
    conversation_history = [
        # System prompt is prepended in get_gemini_response, so history starts clean
    ]
    # Add a welcome message based on the new state
    welcome_translated = f"Hello! I’m your Personal AI Assistant, currently set as a **{personality}**. How can I help you today?" # Use English welcome for simplicity, Gemini will translate the first real response
    conversation_history.append(types.Content(role="model", parts=[types.Part(text=welcome_translated)]))


# --- Get Gemini response with enforced language/personality ---
def get_gemini_response(history, user_input, language, personality):
    global client
    if client is None:
        return "🤖 Error: Gemini client not initialized. Check server logs."

    try:
        # 1. Always rebuild prompt before each message to force language/personality
        system_prompt = build_system_prompt(language, personality)

        # 2. Prepare contents: [System Prompt, History, User Input]
        # Note: History only stores past user/model turns, the system prompt is a new Content object each time.
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

        # 3. Add the successful turn to history for memory
        history.append(types.Content(role="user", parts=[types.Part(text=user_input)]))
        history.append(response.candidates[0].content)

        return response.text.strip()
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return "🤖 Error: Could not contact Gemini model."


# --- Initialize on startup ---
reset_conversation(user_language, user_personality)

# --- Flask endpoint for chatbot ---
@app.route('/chatbot', methods=['POST'])
def get_chat_response():
    global conversation_history, user_language, user_personality

    data = request.get_json()
    user_input = data.get('user_input', '').strip()
    selected_language = data.get('language', user_language)
    selected_personality = data.get('personality', user_personality) # NEW: Get personality
    user_input_lower = user_input.lower()
    
    # --- Check for language or personality change ---
    is_state_change = (selected_language != user_language) or (selected_personality != user_personality)

    if is_state_change:
        # Update global state
        user_language = selected_language
        user_personality = selected_personality
        print(f"🌐 State switched: Lang={user_language}, Pers={user_personality}")
        
        # Reset conversation with new context
        reset_conversation(user_language, user_personality)
        
        # Get a localized/personalized greeting
        initial_message = f"Hello! I've set my language to **{user_language}** and I'm now your **{user_personality}**."
        
        # Use Gemini to translate or rephrase if needed, but for simplicity, we'll keep it mostly English for the control message.
        if user_language != 'English':
             # This is complex, better to let the next user message handle the real translation
             pass

        return jsonify({
            'response': initial_message,
            'language': user_language,
            'personality': user_personality
        })


    # --- Reset command ---
    if any(k in user_input_lower for k in ["reset", "cancel", "stop", "start over", "auto_reset_scroll"]):
        reset_conversation(user_language, user_personality)
        
        # Special case for Flutter's "auto_reset_scroll" (silent reset)
        if user_input_lower == "auto_reset_scroll":
            return jsonify({'response': '...', 'silent': True}) # Return minimal response for timeout

        return jsonify({'response': f"🔄 Conversation reset. I'm now your **{user_personality}** in **{user_language}**.", 'language': user_language})

    # --- Normal chat response ---
    bot_response = get_gemini_response(conversation_history, user_input, user_language, user_personality)
    return jsonify({'response': bot_response, 'language': user_language, 'personality': user_personality})


# --- Flask endpoints for server status (Unchanged) ---
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "✅ Server is running successfully!",
        "message": "Welcome to Personal AI Chatbot API",
        "endpoints": {
            "POST": "/chatbot"
        }
    })

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'status': '✅ Server is running',
        'model': 'Gemini 2.5 Flash',
        'language': user_language,
        'personality': user_personality
    }), 200


# --- Run Flask app ---
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)