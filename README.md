# 🏫 ManthanPollQuizBot  

Telegram Poll/Quiz Bot connected with Google Sheets – specially designed for **Manthan Competition Classes**.  
यह Bot Telegram पर Quiz & Poll create करता है और responses को Google Sheet में record करता है।  

---

## ✨ Features
- ✅ Coaching name automatically दिखता है हर Question के ऊपर  
- ✅ Emoji reactions (👍 ❤️ 😂 😡) for every poll  
- ✅ Google Sheet से direct question fetch करता है  
- ✅ Auto generates Question ID & Student link  
- ✅ QuizID के हिसाब से एक साथ multiple questions भेज सकता है  
- ✅ Votes & Reactions का Live count update होता है  

---

## 📂 Google Sheet Structure
Bot इस format की sheet से data पढ़ता है:

| ID | Question | Option1 | Option2 | Option3 | Option4 | CorrectOption | QuizID | PollID | ChatID | MessageID | ResultsMessageID | Link | CreatedAt |
|----|----------|---------|---------|---------|---------|---------------|--------|--------|--------|-----------|------------------|------|-----------|
| Q1 | भारत की राजधानी क्या है? | मुंबई | दिल्ली | कोलकाता | चेन्नई | 2 | A1 | ... | ... | ... | ... | ... | ... |

---

## 🚀 Deployment Guide  

### 1. Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/ManthanPollQuizBot.git
cd ManthanPollQuizBot
