# run.py
import eventlet # Eventlet को पहले इम्पोर्ट करें
eventlet.monkey_patch() # <<<--- यह बिल्कुल पहली एक्जीक्यूटेबल लाइन होनी चाहिए

# अब बाकी इम्पोर्ट्स करें
from tubealgo import create_app

app = create_app()
# celery ऑब्जेक्ट को app से प्राप्त करना ज़रूरी है अगर Celery ऐप फैक्टरी पैटर्न में बनाया गया है
# celery = app.celery # यह लाइन ज़रूरी हो सकती है, __init__.py पर निर्भर करता है

if __name__ == '__main__':
    # debug=True को प्रोडक्शन में False या हटा देना चाहिए
    app.run(debug=False)
