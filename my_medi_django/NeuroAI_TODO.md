# Neuro AI Upgrade TODO

## 1. Dependencies & Config [IN PROGRESS]
- [ ] pip install google-generativeai Pillow
- [ ] Update settings.py (MEDIA_ROOT/URL, GEMINI_API_KEY)

## 2. Model Updates
- [ ] api/models.py (Medicine: image, working_mechanism, side_effects, is_taken)

## 3. Views & AI
- [ ] api/views.py (analyze_medicine Gemini, update MedicineListCreateView POST, reminder_speech)

## 4. URLs
- [ ] api/urls.py (new paths)
- [ ] my_medi_backend/urls.py (serve media)

## 5. Deploy & Test
- [ ] makemigrations api
- [ ] migrate
- [ ] Add GEMINI_API_KEY to .env
- [ ] Test /api/analyze-medicine/ (POST image/text), /api/reminder-speech/1/
