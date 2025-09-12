from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from aiohttp import web

# Метрики
bot_requests_total = Counter('bot_requests_total', 'Total number of requests to the bot', ['method', 'status'])
bot_active_users = Counter('bot_active_users', 'Number of active users')
bot_forecasts_total = Counter('bot_forecasts_total', 'Number of forecasts generated', ['pair', 'timeframe', 'action'])

async def metrics(request):
    resp = web.Response(body=generate_latest())
    resp.content_type = CONTENT_TYPE_LATEST
    return resp

def start_metrics_server():
    app = web.Application()
    app.router.add_get('/metrics', metrics)
    web.run_app(app, host='0.0.0.0', port=8000)
