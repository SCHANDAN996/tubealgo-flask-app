# gunicorn.conf.py
import multiprocessing

# वर्कर क्लास को gevent पर सेट करें
worker_class = 'gevent'

# वर्कर की संख्या (Render Free टियर के लिए 1 ठीक है)
workers = 1

# ऐप कहाँ बाइंड करना है (Render इसे अनदेखा करेगा और अपने पोर्ट का उपयोग करेगा, लेकिन यह स्थानीय परीक्षण के लिए अच्छा है)
bind = '0.0.0.0:8000'

# लॉगिंग (वैकल्पिक, लेकिन मददगार)
loglevel = 'info'
accesslog = '-' # stdout पर लॉग करें
errorlog = '-'  # stderr पर लॉग करें
