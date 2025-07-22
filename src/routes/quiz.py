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

        # Only one call to the model
        response = client.chat.completions.create(
            model="gpt-4o-preview",  # or "gpt-3.5-turbo" if using 3.5
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
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            json_str = response_text[start_idx:end_idx]
            quiz_data = json.loads(json_str)
            return quiz_data['questions']

        except Exception as e:
            print(f"JSON parsing error: {str(e)}")
            return generate_mock_questions(question_count, custom_prompt)

    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return generate_mock_questions(question_count, custom_prompt)
