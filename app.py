from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt
import speech_recognition as sr
import os
import numpy as np
from scipy.io import wavfile
from nltk.sentiment import SentimentIntensityAnalyzer
import librosa
from pydub import AudioSegment
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import send_from_directory, current_app
import requests
import whisper
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import language_tool_python
import numpy as np
import librosa
from datetime import datetime

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

whisper_model = whisper.load_model("small")
sentiment_analyzer = SentimentIntensityAnalyzer()
grammar_tool = language_tool_python.LanguageTool('en-US')

# Secret key for session
app.secret_key = 'ipd_speakboost_secret_key'

# MySQL configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'speakboost_user'
app.config['MYSQL_PASSWORD'] = 'ipd_password'
app.config['MYSQL_DB'] = 'speakboost'

mysql = MySQL(app)

# Ensure the uploads directory exists
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Generate a unique avatar URL using Multiavatar API (using username for uniqueness)
        avatar_url = f"https://api.multiavatar.com/{username}.svg"  # Unique avatar URL
        
        # Hash password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Insert data into the database without role
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO users (username, email, password, avatar_url, role) VALUES (%s, %s, %s, %s, %s)", 
                    (username, email, hashed_password, avatar_url, None))  # Leave role as None
        mysql.connection.commit()
        cur.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('login'))  # Redirect to login page after registration

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Check if email or password are missing
        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return redirect(url_for('login'))

        cur = mysql.connection.cursor()
        # Only fetch username and password hash to reduce unnecessary data retrieval
        cur.execute("SELECT id, username, password FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()

        # Check if user exists and password is correct
        if user and bcrypt.check_password_hash(user[2], password):  # user[2] is the hashed password
            session['user_id'] = user[0]  # Store user ID in session
            session['username'] = user[1]  # Store username in session
            flash("Login successful!", "success")
            return redirect(url_for('set_role'))  # Redirect to role setup page if necessary
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for('login'))  # Redirect back to login page in case of invalid credentials

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# Convert float32 values to float to ensure JSON serialization
def convert_floats(obj):
    if isinstance(obj, dict):
        return {k: convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats(i) for i in obj]
    elif isinstance(obj, np.float32):
        return float(obj)
    return obj

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/set_role', methods=['GET', 'POST'])
def set_role():
    if 'user_id' not in session:
        flash("Please log in to set your role.", "warning")
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = session.get('user_id')
        
        # Collect all profile information
        role = request.form['role']
        age = request.form['age']
        interests = request.form['interests']
        communication_rating = request.form['communication_rating']

        # Update the user's profile in the database
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE users 
            SET role = %s, age = %s, interests = %s, communication_rating = %s 
            WHERE id = %s
        """, (role, age, interests, communication_rating, user_id))
        mysql.connection.commit()
        cur.close()

        flash("Profile updated successfully!", "success")
        return redirect(url_for('speech-analysis'))

    return render_template('set_role.html')

@app.route('/profile')
def profile():
    if 'user_id' not in session:  # Check if the user is logged in
        flash("Please log in to view your profile.", "warning")
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # Fetch the user's info from the database (username, avatar_url, and role)
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url, role, age, interests, communication_rating FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()

    if user:
        username = user[0]
        avatar_url = user[1] if user[1] else 'https://api.multiavatar.com/default.svg'  # Default avatar if None
        role = user[2] if user[2] else 'Not specified'  # Default to 'Not specified' if no role is set
        age = user[3] if user[3] else 'Not specified'  # Default
        interests = user[4] if user[4] else 'Not specified'  # Default
        communication_rating = user[5] if user[5] else 'Not specified'  #

    else:
        username = "Unknown"
        avatar_url = 'https://api.multiavatar.com/default.svg'  # Default avatar URL
        role = 'Not specified'
        age = 'Not specified'
        interests = 'Not specified'
        communication_rating = 'Not specified'
    
    return render_template('profile.html', username=username, avatar_url=avatar_url, role=role
                               , age=age, interests=interests, communication_rating=communication_rating)
    
# New route specifically for speech analysis
@app.route('/speech-analysis')
def speech_analysis():
    if 'user_id' not in session:
        flash("Please log in to access speech analysis.", "warning")
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    
    # Fetch username and avatar URL from the database
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url, role FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()

    if user:
        username = user[0]
        avatar_url = user[1]  # This will now be the avatar URL
        role = user[2]  # The role field
    else:
        username = "Unknown"
        avatar_url = "https://api.multiavatar.com/default.svg"  # Default avatar URL
        role = "Unknown"  # Default role if none found

    return render_template('speech_analysis.html', username=username, avatar_url=avatar_url, role=role)

def analyze_speech(audio_file_path):
    """Analyze speech from an audio file and return comprehensive analysis."""
    
    # Transcribe audio
    result = whisper_model.transcribe(audio_file_path)
    transcript = result["text"]
    
    # Load audio for analysis
    y, sr = librosa.load(audio_file_path)
    duration = librosa.get_duration(y=y, sr=sr)
    
    # Calculate words per minute
    words = len(transcript.split())
    wpm = (words / duration) * 60
    
    # Analyze filler words
    filler_words = ["um", "uh", "like", "you know", "actually", "basically", "literally", "seriously"]
    filler_count = sum(1 for word in transcript.lower().split() if word in filler_words)
    filler_percentage = filler_count / words if words > 0 else 0
    
    # Sentiment analysis
    sentiment_scores = sentiment_analyzer.polarity_scores(transcript)
    
    # Grammar check
    grammar_matches = grammar_tool.check(transcript)
    structure_issues = [
        {
            'context': match.context,
            'message': match.message,
            'suggestions': match.replacements if match.replacements else ["Rephrase for clarity"]
        }
        for match in grammar_matches
    ]
    
    # Audio characteristics
    energy = np.mean(librosa.feature.rms(y=y))
    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
    pitch = np.mean(pitches[pitches > 0]) if len(pitches[pitches > 0]) > 0 else 0
    
    return {
        'transcript': transcript,
        'words_per_minute': float(wpm),
        'filler_count': filler_count,
        'filler_percentage': float(filler_percentage),
        'sentiment': sentiment_scores,
        'structure_issues': structure_issues,
        'audio_characteristics': {
            'energy': float(energy),
            'pitch': float(pitch),
            'duration': float(duration)
        }
    }

@app.route('/speak', methods=['POST'])
def speak():
    """Route to handle text-to-speech requests"""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': 'No text provided'}), 400
    
    text = data['text']
    return jsonify({
        'success': True,
        'text': text
    })

@app.route('/speech_analysis_page')
def speech_analysis_page():
    if 'user_id' not in session:
        flash("Please log in to access speech analysis.", "warning")
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    
    # Fetch user data
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    
    username = user[0] if user else "Unknown"
    avatar_url = user[1] if user and user[1] else 'https://api.multiavatar.com/default.svg'
    
    return render_template('speech_analysis.html', username=username, avatar_url=avatar_url)

@app.route('/process_speech_analysis', methods=['POST'])
def process_speech_analysis():
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    audio_file = request.files['file']
    if audio_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Create a unique filename using timestamp and user_id
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        user_id = session['user_id']
        filename = f'speech_analysis_{user_id}_{timestamp}.wav'
        audio_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the uploaded file
        audio_file.save(audio_file_path)
        
        # Analyze the audio
        analysis_results = analyze_speech(audio_file_path)
        
        # Store the analysis results in the database
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO speech_analysis_reports 
            (user_id, transcript, words_per_minute, filler_count, 
            sentiment_compound, audio_energy, audio_pitch, timestamp) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            session['user_id'],
            analysis_results['transcript'],
            analysis_results['words_per_minute'],
            analysis_results['filler_count'],
            analysis_results['sentiment']['compound'],
            analysis_results['audio_characteristics']['energy'],
            analysis_results['audio_characteristics']['pitch']
        ))
        mysql.connection.commit()
        cur.close()
        
        # Clean up the audio file
        os.remove(audio_file_path)
        
        # Convert numpy values to Python native types for JSON serialization
        analysis_results = convert_floats(analysis_results)
        
        return jsonify(analysis_results), 200

    except Exception as e:
        print(f"Error in speech analysis: {str(e)}")
        if os.path.exists(audio_file_path):
            os.remove(audio_file_path)
        return jsonify({'error': str(e)}), 500

@app.route('/reports')
def view_reports():
    if 'user_id' not in session:
        flash('Please log in to view your reports', 'error')
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    
    # Fetch username and avatar URL from the database
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()

    if user:
        username = user[0]
        avatar_url = user[1]  # This will now be the avatar URL
    else:
        username = "Unknown"
        avatar_url = "https://api.multiavatar.com/default.svg"  # Default avatar URL
    
    # Fetch reports from the database for the logged-in user
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT * FROM speech_analysis_reports 
        WHERE user_id = %s 
        ORDER BY timestamp DESC
    """, (user_id,))
    
    # Get column names
    columns = [column[0] for column in cur.description]
    
    # Convert to list of dictionaries
    reports = [dict(zip(columns, row)) for row in cur.fetchall()]
    
    cur.close()

    return render_template('reports.html', reports=reports, username=username, avatar_url=avatar_url)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:  # Check if the user is logged in
        flash("Please log in to access the dashboard.", "warning")
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    
    # Fetch username and avatar URL from the database
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url, role FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()

    if user:
        username = user[0]
        avatar_url = user[1]  # This will now be the avatar URL
        role = user[2]  # The role field
    else:
        username = "Unknown"
        avatar_url = "https://api.multiavatar.com/default.svg"  # Default avatar URL
        role = "Unknown"  # Default role if none found

    return render_template('dashboard.html', username=username, avatar_url=avatar_url, role=role)

@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    audio_file = request.files['file']

    if audio_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    audio_file_path = os.path.join(UPLOAD_FOLDER, audio_file.filename)

    try:
        audio_file.save(audio_file_path)
        
        # Analyze the uploaded audio file
        transcript, analysis_result = analyze_audio(audio_file_path)

        # Ensure that any float32 values are converted
        response_data = {
            'transcript': transcript,
            **convert_floats(analysis_result)
        }

        return jsonify(response_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500  # Return the error message

@app.route('/analyze_real_time', methods=['POST'])
def analyze_real_time():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    audio_file = request.files['file']

    if audio_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    audio_file_path = os.path.join(UPLOAD_FOLDER, audio_file.filename)

    try:
        # Save the uploaded file
        audio_file.save(audio_file_path)

        # Log the file type for debugging purposes
        print(f"File type: {audio_file.content_type}")
        print(f"File size: {os.path.getsize(audio_file_path)} bytes")
        
        # Ensure the file is a valid WAV format by converting to standard WAV
        audio = AudioSegment.from_file(audio_file_path)
        converted_audio_path = audio_file_path.replace(".wav", "_converted.wav")
        audio.export(converted_audio_path, format="wav")

        # Now analyze the properly converted WAV file
        transcript, analysis_result = analyze_audio(converted_audio_path)

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO user_reports 
            (user_id, transcript, words_per_minute, tone_energy, pitch, pace, 
            sentiment_positive, sentiment_negative, timestamp) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            session['user_id'], 
            transcript, 
            analysis_result['words_per_minute'],
            analysis_result['tone']['energy'],
            analysis_result['pitch'],
            analysis_result['pace'],
            analysis_result['sentiment']['positive'] * 100,
            analysis_result['sentiment']['negative'] * 100
        ))
        mysql.connection.commit()
        cur.close()

        # Convert float32 values before returning
        response_data = {
            'transcript': transcript,
            **convert_floats(analysis_result)
        }

        return jsonify(response_data), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

def analyze_audio(file_path):
    recognizer = sr.Recognizer()
    # Get transcript from audio
    with sr.AudioFile(file_path) as source:
        audio = recognizer.record(source)  # Read the entire audio file
        try:
            # Use Google Web Speech API for transcription
            transcript = recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            transcript = "Could not understand audio."
        except sr.RequestError:
            transcript = "Could not request results from the service."

    # Perform actual analysis
    analysis = {
        'words_per_minute': calculate_wpm(transcript, file_path),
        'tone': analyze_tone(file_path),  # Analyze tone
        'pitch': analyze_pitch(file_path),  # Analyze pitch
        'pace': analyze_pace(transcript),  # Analyze pace
        'sentiment': analyze_sentiment(transcript)  # Analyze sentiment
    }

    return transcript, analysis

@app.route('/exercises')
def exercises():
    if 'user_id' not in session:
        flash("Please log in to access exercises.", "warning")
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    
    # Fetch user data
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    
    username = user[0] if user else "Unknown"
    avatar_url = user[1] if user and user[1] else 'https://api.multiavatar.com/default.svg'
    
    # Hardcoded exercises data with multiple choice options
    exercises_data = [
        {
            "id": 1,
            "question": "Which of the following is the most effective way to show active listening?",
            "options": [
                "Interrupting with your own story",
                "Nodding and maintaining eye contact",
                "Looking at your phone occasionally",
                "Thinking about your response while they speak"
            ],
            "correct": 1,  # Index of correct answer
            "category": "Active Listening"
        },
        {
            "id": 2,
            "question": "What is the best approach when giving constructive feedback?",
            "options": [
                "Wait until you're angry to address issues",
                "Focus on personal characteristics",
                "Be specific and focus on behaviors",
                "Give feedback in public settings"
            ],
            "correct": 2,
            "category": "Feedback Skills"
        },
        {
            "id": 3,
            "question": "How can you improve your non-verbal communication?",
            "options": [
                "Cross your arms to show confidence",
                "Avoid eye contact to seem mysterious",
                "Keep a neutral face at all times",
                "Mirror the other person's body language appropriately"
            ],
            "correct": 3,
            "category": "Body Language"
        },
        {
            "id": 4,
            "question": "What is the best way to handle disagreements in a conversation?",
            "options": [
                "Stand your ground and never compromise",
                "Listen to understand and find common ground",
                "Change the subject immediately",
                "Agree with everything to avoid conflict"
            ],
            "correct": 1,
            "category": "Conflict Resolution"
        },
        {
            "id": 5,
            "question": "Which communication channel is most appropriate for delivering sensitive feedback?",
            "options": [
                "Email",
                "Text message",
                "Face-to-face conversation",
                "Group chat"
            ],
            "correct": 2,
            "category": "Communication Channels"
        },
        {
            "id": 6,
            "question": "What is the most effective way to start a presentation?",
            "options": [
                "Apologize for being nervous",
                "Start with a compelling story or statistic",
                "Read directly from your slides",
                "Give a detailed personal introduction"
            ],
            "correct": 1,
            "category": "Public Speaking"
        },
        {
            "id": 7,
            "question": "How can you best handle interruptions during a conversation?",
            "options": [
                "Stop talking immediately",
                "Talk louder to be heard",
                "Ignore the interruption completely",
                "Politely acknowledge and redirect back to the topic"
            ],
            "correct": 3,
            "category": "Conversation Skills"
        }
    ]
    
    return render_template('exercises.html', 
                         exercises=exercises_data, 
                         username=username, 
                         avatar_url=avatar_url)

def calculate_wpm(transcript, file_path):
    words = len(transcript.split())
    # Get audio duration in seconds
    sample_rate, samples = wavfile.read(file_path)
    duration = len(samples) / sample_rate  # Duration in seconds
    wpm = words / (duration / 60)
    return wpm

def analyze_tone(file_path):
    # Load the audio file
    y, sr = librosa.load(file_path)
    
    # Calculate the energy of the audio signal
    energy = np.mean(librosa.feature.rms(y=y))

    # Tone can be represented by energy levels
    tone_analysis = {
        'energy': energy
    }
    return tone_analysis

def analyze_pitch(file_path):
    # Load the audio file
    y, sr = librosa.load(file_path)

    # Extract pitches
    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)

    # Calculate average pitch
    avg_pitch = np.mean(pitches[pitches > 0])  # Ignore zero values
    return avg_pitch

def analyze_pace(transcript):
    words = len(transcript.split())
    return words / (len(transcript.split()) * 0.5)  # Average pace as words per second

def analyze_sentiment(transcript):
    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(transcript)
    return {
        'positive': sentiment['pos'],
        'negative': sentiment['neg'],
        'neutral': sentiment['neu'],
        'compound': sentiment['compound']
    }

if __name__ == '__main__':
    app.run(debug=True)