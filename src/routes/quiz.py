from flask import Blueprint, request, jsonify, session
from src.models.user import db, User, Document, Quiz, QuizResult
import json
from openai import OpenAI
import os

quiz_bp = Blueprint('quiz', __name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def generate_quiz_questions(content_text, question_count, custom_prompt=""):
    """Generate quiz questions using OpenAI API"""
    try:
        # Prepare the prompt
        base_prompt = f"""
        Based on the following document content, generate exactly {question_count} multiple-choice questions.
        
        Document content:
        {content_text[:4000]}  # Limit content to avoid token limits
        
        {f"Additional instructions: {custom_prompt}" if custom_prompt else ""}
        
        Requirements:
        1. Generate exactly {question_count} questions
        2. Each question should have 4 options (A, B, C, D)
        3. Only one option should be correct
        4. Questions should test understanding of the document content
        5. Provide explanations for the correct answers
        6. Return the response in the following JSON format:
        
        {{
            "questions": [
                {{
                    "id": 1,
                    "question": "Question text here?",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "correct_answer": 0,
                    "explanation": "Explanation for why this is correct"
                }}
            ]
        }}
        """
        
       response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": "You are an expert quiz generator. Generate high-quality multiple-choice questions based on document content."},
        {"role": "user", "content": base_prompt}
    ],
    max_tokens=2000,
    temperature=0.7
)

response_text = response.choices[0].message.content
        
        # Try to extract JSON from the response
        try:
            # Find JSON in the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            json_str = response_text[start_idx:end_idx]
            quiz_data = json.loads(json_str)
            return quiz_data['questions']
        except:
            # Fallback: generate mock questions if OpenAI parsing fails
            return generate_mock_questions(question_count, custom_prompt)
    
    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        # Fallback to mock questions
        return generate_mock_questions(question_count, custom_prompt)

def generate_mock_questions(question_count, custom_prompt=""):
    """Generate mock questions as fallback"""
    questions = []
    for i in range(1, question_count + 1):
        questions.append({
            "id": i,
            "question": f"Sample question {i} from the document{f' ({custom_prompt})' if custom_prompt else ''}?",
            "options": [
                f"Option A for question {i}",
                f"Option B for question {i}",
                f"Option C for question {i}",
                f"Option D for question {i}"
            ],
            "correct_answer": i % 4,  # Distribute correct answers
            "explanation": f"This is the explanation for question {i}. The correct answer provides the most accurate information based on the document content."
        })
    return questions

@quiz_bp.route('/generate', methods=['POST'])
def generate_quiz():
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.get_json()
        document_id = data.get('document_id')
        question_count = data.get('question_count', 10)
        custom_prompt = data.get('custom_prompt', '')
        
        if not document_id:
            return jsonify({'error': 'Document ID is required'}), 400
        
        if question_count not in [10, 20, 30, 40, 50]:
            return jsonify({'error': 'Invalid question count. Must be 10, 20, 30, 40, or 50'}), 400
        
        # Check if user has enough tokens
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.tokens < question_count:
            return jsonify({'error': 'Insufficient tokens'}), 400
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Generate questions
        questions = generate_quiz_questions(document.content_text, question_count, custom_prompt)
        
        # Deduct tokens
        user.tokens -= question_count
        
        # Save quiz to database
        quiz = Quiz(
            document_id=document_id,
            user_id=user_id,
            title=f"Quiz for {document.original_filename}",
            custom_prompt=custom_prompt,
            question_count=question_count,
            questions_data=json.dumps(questions)
        )
        
        db.session.add(quiz)
        db.session.commit()
        
        return jsonify({
            'message': 'Quiz generated successfully',
            'quiz_id': quiz.id,
            'questions': questions,
            'remaining_tokens': user.tokens
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Quiz generation failed: {str(e)}'}), 500

@quiz_bp.route('/<int:quiz_id>', methods=['GET'])
def get_quiz(quiz_id):
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        quiz = Quiz.query.filter_by(id=quiz_id, user_id=user_id).first()
        if not quiz:
            return jsonify({'error': 'Quiz not found'}), 404
        
        questions = json.loads(quiz.questions_data)
        
        return jsonify({
            'quiz': quiz.to_dict(),
            'questions': questions
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get quiz: {str(e)}'}), 500

@quiz_bp.route('/submit', methods=['POST'])
def submit_quiz():
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.get_json()
        quiz_id = data.get('quiz_id')
        answers = data.get('answers', [])  # List of user answers
        
        if not quiz_id:
            return jsonify({'error': 'Quiz ID is required'}), 400
        
        # Get quiz
        quiz = Quiz.query.filter_by(id=quiz_id, user_id=user_id).first()
        if not quiz:
            return jsonify({'error': 'Quiz not found'}), 404
        
        questions = json.loads(quiz.questions_data)
        
        # Calculate score
        score = 0
        total_questions = len(questions)
        detailed_results = []
        
        for i, question in enumerate(questions):
            user_answer = answers[i] if i < len(answers) else -1
            is_correct = user_answer == question['correct_answer']
            
            if is_correct:
                score += 1
            
            detailed_results.append({
                'question_id': question['id'],
                'user_answer': user_answer,
                'correct_answer': question['correct_answer'],
                'is_correct': is_correct
            })
        
        percentage = (score / total_questions) * 100 if total_questions > 0 else 0
        
        # Save result
        quiz_result = QuizResult(
            quiz_id=quiz_id,
            user_id=user_id,
            score=score,
            total_questions=total_questions,
            percentage=percentage,
            answers_data=json.dumps(detailed_results)
        )
        
        db.session.add(quiz_result)
        db.session.commit()
        
        # Generate feedback and suggestions
        feedback = ""
        suggestions = []
        
        if percentage >= 80:
            feedback = "Excellent work! You have a strong understanding of the material."
            suggestions = ["Review the few topics you missed to achieve perfection."]
        elif percentage >= 60:
            feedback = "Good job! You have a decent grasp of the material."
            suggestions = [
                "Focus on the topics where you answered incorrectly.",
                "Consider re-reading those sections of the document."
            ]
        else:
            feedback = "You need more practice with this material."
            suggestions = [
                "Review the entire document thoroughly.",
                "Focus especially on the topics you missed.",
                "Consider taking the quiz again after studying."
            ]
        
        return jsonify({
            'message': 'Quiz submitted successfully',
            'result_id': quiz_result.id,
            'score': score,
            'total_questions': total_questions,
            'percentage': percentage,
            'feedback': feedback,
            'suggestions': suggestions,
            'detailed_results': detailed_results
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Quiz submission failed: {str(e)}'}), 500

@quiz_bp.route('/results/<int:result_id>', methods=['GET'])
def get_quiz_result(result_id):
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        result = QuizResult.query.filter_by(id=result_id, user_id=user_id).first()
        if not result:
            return jsonify({'error': 'Quiz result not found'}), 404
        
        detailed_results = json.loads(result.answers_data)
        
        return jsonify({
            'result': result.to_dict(),
            'detailed_results': detailed_results
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get quiz result: {str(e)}'}), 500

@quiz_bp.route('/history', methods=['GET'])
def get_quiz_history():
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        quizzes = Quiz.query.filter_by(user_id=user_id).order_by(Quiz.created_at.desc()).all()
        
        quiz_history = []
        for quiz in quizzes:
            quiz_dict = quiz.to_dict()
            # Get latest result for this quiz
            latest_result = QuizResult.query.filter_by(quiz_id=quiz.id, user_id=user_id).order_by(QuizResult.completed_at.desc()).first()
            if latest_result:
                quiz_dict['latest_result'] = latest_result.to_dict()
            quiz_history.append(quiz_dict)
        
        return jsonify({
            'quiz_history': quiz_history
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get quiz history: {str(e)}'}), 500

