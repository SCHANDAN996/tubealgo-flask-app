# gunicorn.conf.py
import multiprocessing

# वर्कर क्लास को gevent पर सेट करें
worker_class = 'gevent'

# वर्कर की संख्या (Render Free टियर के लिए 1 ठीक है)
workers = 1

# ऐप कहाँ बाइंड करना है (Render इसे अनदेखा करेगा और अपने पोर्ट का उपयोग करेगा)
bind = '0.0.0.0:10000' # Render आमतौर पर पोर्ट 10000 का उपयोग करता है

# लॉगिंग
loglevel = 'info'
accesslog = '-' # stdout पर लॉग करें
errorlog = '-'  # stderr पर लॉग करें

# ग्रेसफुल शटडाउन टाइमआउट (सेकंड में) - वर्कर्स को बंद होने के लिए अधिक समय दें
graceful_timeout = 60 # <<<--- यह लाइन जोड़ी गई है
