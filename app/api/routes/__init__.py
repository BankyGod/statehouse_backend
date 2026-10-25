from fastapi import APIRouter

from app.api.routes import (
    activities,
    auth,
    bank,
    businesses,
    cabinet,
    characters,
    chat,
    crime,
    education,
    gym,
    housing,
    inventory,
    jail,
    jobs,
    legislation,
    medical,
    news,
    permits,
    politics,
    social,
    states,
    stocks,
    travel,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(states.router)
api_router.include_router(characters.router)
api_router.include_router(education.router)
api_router.include_router(jobs.router)
api_router.include_router(permits.router)
api_router.include_router(businesses.router)
api_router.include_router(crime.router)
api_router.include_router(travel.router)
api_router.include_router(bank.router)
api_router.include_router(housing.router)
api_router.include_router(medical.router)
api_router.include_router(politics.router)
api_router.include_router(legislation.router)
api_router.include_router(news.router)
api_router.include_router(cabinet.router)
api_router.include_router(chat.router)
api_router.include_router(stocks.router)
api_router.include_router(activities.router)
api_router.include_router(gym.router)
api_router.include_router(inventory.router)
api_router.include_router(jail.router)
api_router.include_router(social.router)
