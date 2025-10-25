# run.py
import gevent.monkey
gevent.monkey.patch_all() # यह पहली एक्जीक्यूटेबल लाइन होनी चाहिए

# अब बाकी इम्पोर्ट्स करें
from tubealgo import create_app, celery as celery_app # celery को भी इम्पोर्ट करें या create_app से लें

app = create_app()
# celery ऑब्जेक्ट को app से प्राप्त करना ज़रूरी है अगर Celery ऐप फैक्टरी पैटर्न में बनाया गया है
celery = app.celery # <<<--- यह लाइन अनकमेंट की गई है

if __name__ == '__main__':
    # debug=True को प्रोडक्शन में False या हटा देना चाहिए
    app.run(debug=False)

