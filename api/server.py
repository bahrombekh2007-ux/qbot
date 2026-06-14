"""Aiohttp REST API - WebApp uchun + static fayllar."""
import logging
import os
from pathlib import Path
from aiohttp import web
from aiohttp_cors import setup as cors_setup, ResourceOptions
import jwt
from datetime import datetime, timedelta
from functools import wraps

from bot.config import settings
from bot.db.session import get_session
from bot.db.models import User, Test, TestAttempt, TestStatus, SubscriptionTier
from bot.services.ai import ai_service
from bot.services.parser import FileParser
from bot.services.subscription import subscription_service
from sqlalchemy import select, desc, and_, func

logger = logging.getLogger(__name__)

# Webapp papkasi
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"


# ============ Authentication ============

def verify_telegram_auth(init_data: str) -> dict:
    """Telegram WebApp initData'ni verify qilish."""
    import hashlib
    import hmac
    import json
    from urllib.parse import parse_qsl

    try:
        parsed = dict(parse_qsl(init_data))
        hash_value = parsed.pop("hash", None)

        if not hash_value:
            raise ValueError("hash yo'q")

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            settings.bot_token.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if calculated_hash != hash_value:
            raise ValueError("Invalid hash")

        user_data = json.loads(parsed.get("user", "{}"))
        return user_data

    except Exception as e:
        logger.error(f"Telegram auth error: {e}")
        raise


def jwt_required(handler):
    """JWT token tekshirish middleware."""
    @wraps(handler)
    async def wrapper(request: web.Request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response({"error": "Unauthorized"}, status=401)

        token = auth_header[7:]
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm]
            )
            request["user_id"] = payload["user_id"]
            request["telegram_id"] = payload["telegram_id"]
        except jwt.ExpiredSignatureError:
            return web.json_response({"error": "Token expired"}, status=401)
        except jwt.InvalidTokenError:
            return web.json_response({"error": "Invalid token"}, status=401)

        return await handler(request)
    return wrapper


# ============ API Handlers ============

async def health(request: web.Request):
    """Health check - Render.com uchun muhim."""
    return web.json_response({
        "status": "ok",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "polling",
    })


async def auth_login(request: web.Request):
    """Telegram WebApp orqali autentifikatsiya.

    POST /api/auth/login
    Body: { "initData": "..." }
    """
    try:
        data = await request.json()
        init_data = data.get("initData", "")

        # Development rejimida bypass
        if not settings.is_production and data.get("dev_mode"):
            user_data = {
                "id": data.get("telegram_id", 123456),
                "first_name": data.get("first_name", "Dev User"),
                "username": data.get("username", "dev"),
                "language_code": "uz",
            }
        else:
            user_data = verify_telegram_auth(init_data)

        telegram_id = user_data["id"]

        async with get_session() as session:
            stmt = select(User).where(User.telegram_id == telegram_id)
            user = (await session.execute(stmt)).scalar_one_or_none()

            is_new = False
            if not user:
                user = User(
                    telegram_id=telegram_id,
                    first_name=user_data.get("first_name", ""),
                    last_name=user_data.get("last_name"),
                    username=user_data.get("username"),
                    language_code=user_data.get("language_code", "uz"),
                    photo_url=user_data.get("photo_url"),
                )
                session.add(user)
                await session.flush()
                await session.refresh(user)
                is_new = True
            else:
                user.last_active = datetime.utcnow()

            token = jwt.encode(
                {
                    "user_id": user.id,
                    "telegram_id": user.telegram_id,
                    "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours),
                    "iat": datetime.utcnow(),
                },
                settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
            )

            tier, limits = await subscription_service.get_user_tier(telegram_id)

            return web.json_response({
                "token": token,
                "user": {
                    "id": user.id,
                    "telegram_id": user.telegram_id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "username": user.username,
                    "language_code": user.language_code,
                    "photo_url": user.photo_url,
                    "subscription_tier": user.subscription_tier.value,
                    "tests_created": user.tests_created,
                    "tests_taken": user.tests_taken,
                    "streak_days": user.streak_days,
                    "is_new": is_new,
                    "limits": limits,
                }
            })
    except Exception as e:
        logger.exception("Auth error")
        return web.json_response({"error": str(e)}, status=400)


@jwt_required
async def api_get_user(request: web.Request):
    """Joriy foydalanuvchi ma'lumotlari."""
    user_id = request["user_id"]

    async with get_session() as session:
        stmt = select(User).where(User.id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user:
            return web.json_response({"error": "User not found"}, status=404)

        tier, limits = await subscription_service.get_user_tier(user.telegram_id)

        return web.json_response({
            "id": user.id,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "language_code": user.language_code,
            "subscription_tier": user.subscription_tier.value,
            "subscription_expires": user.subscription_expires.isoformat() if user.subscription_expires else None,
            "trial_used": user.trial_used,
            "tests_created": user.tests_created,
            "tests_taken": user.tests_taken,
            "total_score": user.total_score,
            "streak_days": user.streak_days,
            "limits": limits,
        })


@jwt_required
async def api_upload_file(request: web.Request):
    """Fayl yuklash va matn ajratish."""
    user_id = request["user_id"]
    telegram_id = request["telegram_id"]

    try:
        reader = await request.multipart()
        field = await reader.next()

        if not field or field.name != "file":
            return web.json_response({"error": "file maydoni topilmadi"}, status=400)

        filename = field.filename or "file"
        file_ext = FileParser.detect_format(filename)
        if not file_ext:
            return web.json_response({
                "error": "Qo'llab-quvvatlanmaydigan format. PDF, DOCX, XLSX, TXT, PPTX yuklang."
            }, status=400)

        # Limit tekshirish
        allowed, reason, stats = await subscription_service.check_quota(telegram_id, user_id)
        if not allowed:
            return web.json_response({"error": reason}, status=429)

        # Faylni o'qish
        content = await field.read()
        max_size = settings.max_file_size_mb * 1024 * 1024
        if len(content) > max_size:
            return web.json_response({
                "error": f"Fayl hajmi katta. Maksimal: {settings.max_file_size_mb} MB"
            }, status=413)

        # Vaqtinchalik saqlash
        import uuid
        os.makedirs("uploads", exist_ok=True)
        tmp_path = Path("uploads") / f"{user_id}_{uuid.uuid4().hex[:8]}_{filename}"
        tmp_path.write_bytes(content)

        try:
            text = await FileParser.extract_text(tmp_path, file_ext)
            file_stats = FileParser.get_file_stats(text)
            lang = await ai_service.detect_language(text)

            if not text or len(text.strip()) < 50:
                return web.json_response({"error": "Faylda yetarli matn topilmadi."}, status=400)

            return web.json_response({
                "success": True,
                "text": text[:500],  # Preview uchun
                "text_full": text,   # Generatsiya uchun
                "filename": filename,
                "file_ext": file_ext,
                "language": lang,
                "stats": file_stats,
                "quota": stats,
            })
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

    except Exception as e:
        logger.exception("Upload error")
        return web.json_response({"error": str(e)[:200]}, status=500)


@jwt_required
async def api_generate_quiz(request: web.Request):
    """Test savollarini generatsiya qilish."""
    user_id = request["user_id"]
    telegram_id = request["telegram_id"]

    try:
        data = await request.json()
        text = data.get("text", "")
        count = min(int(data.get("count", 10)), settings.max_questions_per_test)
        language = data.get("language", "uz")
        difficulty = data.get("difficulty", "mixed")
        title = data.get("title", "Test")
        source_file = data.get("source_file", "")
        source_type = data.get("source_type", "txt")

        if not text or len(text.strip()) < 50:
            return web.json_response({"error": "Matn juda qisqa"}, status=400)

        # Tariff limiti
        tier, limits = await subscription_service.get_user_tier(telegram_id)
        if count > limits["max_questions"]:
            count = limits["max_questions"]

        # Generatsiya
        questions = await ai_service.generate_questions(
            text=text,
            count=count,
            language=language,
            difficulty=difficulty,
        )

        if not questions:
            return web.json_response({"error": "Savol yaratib bo'lmadi. Boshqa matn yuklang."}, status=400)

        # Bazaga saqlash
        async with get_session() as session:
            test = Test(
                user_id=user_id,
                title=title or Path(source_file).stem or "Test",
                source_file=source_file,
                source_type=source_type,
                questions={"items": questions, "version": 1},
                total_questions=len(questions),
                status=TestStatus.READY,
            )
            session.add(test)
            await session.flush()
            await session.refresh(test)
            test_id = test.id

            # User statistikasi
            user = await session.get(User, user_id)
            if user:
                user.tests_created = (user.tests_created or 0) + 1

        # Usage +1
        await subscription_service.increment_usage(user_id, len(questions))

        return web.json_response({
            "success": True,
            "test_id": test_id,
            "title": title,
            "questions": questions,
            "total_questions": len(questions),
        })

    except Exception as e:
        logger.exception("Generate error")
        return web.json_response({"error": str(e)[:200]}, status=500)


@jwt_required
async def api_get_tests(request: web.Request):
    """Foydalanuvchining testlari."""
    user_id = request["user_id"]
    page = int(request.query.get("page", 1))
    per_page = min(int(request.query.get("per_page", 20)), 50)
    offset = (page - 1) * per_page

    async with get_session() as session:
        stmt = (
            select(Test)
            .where(Test.user_id == user_id)
            .order_by(desc(Test.created_at))
            .offset(offset)
            .limit(per_page)
        )
        result = await session.execute(stmt)
        tests = result.scalars().all()

        total = await session.scalar(
            select(func.count(Test.id)).where(Test.user_id == user_id)
        )

        return web.json_response({
            "tests": [
                {
                    "id": t.id,
                    "title": t.title,
                    "total_questions": t.total_questions,
                    "status": t.status.value,
                    "times_taken": t.times_taken,
                    "avg_score": t.avg_score,
                    "created_at": t.created_at.isoformat(),
                    "share_code": t.share_code,
                } for t in tests
            ],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total or 0,
                "pages": ((total or 0) + per_page - 1) // per_page,
            }
        })


@jwt_required
async def api_get_test(request: web.Request):
    """Bitta testni olish."""
    user_id = request["user_id"]
    test_id = int(request.match_info["test_id"])

    async with get_session() as session:
        test = await session.get(Test, test_id)
        if not test:
            return web.json_response({"error": "Test topilmadi"}, status=404)

        # Public test yoki o'zining testi
        if test.user_id != user_id and not test.is_public:
            return web.json_response({"error": "Ruxsat yo'q"}, status=403)

        return web.json_response({
            "id": test.id,
            "title": test.title,
            "questions": test.questions.get("items", []),
            "total_questions": test.total_questions,
            "time_limit": test.time_limit_seconds,
            "passing_score": test.passing_score,
            "status": test.status.value,
            "times_taken": test.times_taken,
            "avg_score": test.avg_score,
        })


@jwt_required
async def api_submit_test(request: web.Request):
    """Test javoblarini qabul qilish va natijani hisoblash."""
    user_id = request["user_id"]
    test_id = int(request.match_info["test_id"])

    try:
        data = await request.json()
        answers = data.get("answers", {})
        time_spent = int(data.get("time_spent", 0))

        async with get_session() as session:
            test = await session.get(Test, test_id)
            if not test:
                return web.json_response({"error": "Test topilmadi"}, status=404)

            questions = test.questions.get("items", [])
            if not questions:
                return web.json_response({"error": "Test bo'sh"}, status=400)

            # Hisoblash
            correct = 0
            detailed = []

            for q in questions:
                qid = str(q["id"])
                user_answer = answers.get(qid)
                is_correct = user_answer == q["correct"]

                if is_correct:
                    correct += 1

                detailed.append({
                    "id": q["id"],
                    "question": q["question"],
                    "options": q["options"],
                    "user_answer": user_answer,
                    "correct_answer": q["correct"],
                    "is_correct": is_correct,
                    "explanation": q.get("explanation", ""),
                })

            total = len(questions)
            score_percent = (correct / total * 100) if total else 0
            passed = score_percent >= test.passing_score

            # Saqlash
            attempt = TestAttempt(
                user_id=user_id,
                test_id=test_id,
                answers=answers,
                correct_count=correct,
                total_questions=total,
                score_percent=score_percent,
                passed=passed,
                time_spent_seconds=time_spent,
                completed_at=datetime.utcnow(),
            )
            session.add(attempt)

            # Test statistikasi
            test.times_taken = (test.times_taken or 0) + 1
            if test.avg_score == 0:
                test.avg_score = score_percent
            else:
                test.avg_score = (test.avg_score + score_percent) / 2

            # User statistikasi
            user = await session.get(User, user_id)
            if user:
                user.tests_taken = (user.tests_taken or 0) + 1
                user.total_score = (user.total_score or 0) + correct

            await session.flush()
            await session.refresh(attempt)

            return web.json_response({
                "success": True,
                "attempt_id": attempt.id,
                "score_percent": round(score_percent, 1),
                "correct_count": correct,
                "total_questions": total,
                "passed": passed,
                "passing_score": test.passing_score,
                "time_spent": time_spent,
                "detailed": detailed,
            })

    except Exception as e:
        logger.exception("Submit error")
        return web.json_response({"error": str(e)[:200]}, status=500)


@jwt_required
async def api_share_test(request: web.Request):
    """Test uchun share code yaratish."""
    user_id = request["user_id"]
    test_id = int(request.match_info["test_id"])

    async with get_session() as session:
        test = await session.get(Test, test_id)
        if not test or test.user_id != user_id:
            return web.json_response({"error": "Test topilmadi"}, status=404)

        if not test.share_code:
            import secrets
            test.share_code = secrets.token_urlsafe(8)[:12]
            test.is_public = True

        share_url = f"https://t.me/{settings.bot_username}?start=test_{test.id}"

        return web.json_response({
            "share_code": test.share_code,
            "share_url": share_url,
            "telegram_url": share_url,
        })


@jwt_required
async def api_get_leaderboard(request: web.Request):
    """Global leaderboard."""
    async with get_session() as session:
        stmt = (
            select(User)
            .order_by(desc(User.total_score))
            .limit(50)
        )
        result = await session.execute(stmt)
        users = result.scalars().all()

        current_user_id = request["user_id"]
        current_rank = None
        for idx, u in enumerate(users, 1):
            if u.id == current_user_id:
                current_rank = idx
                break

        return web.json_response({
            "leaders": [
                {
                    "rank": idx,
                    "first_name": u.first_name,
                    "username": u.username,
                    "photo_url": u.photo_url,
                    "total_score": u.total_score,
                    "tests_taken": u.tests_taken,
                    "is_you": u.id == current_user_id,
                } for idx, u in enumerate(users, 1)
            ],
            "your_rank": current_rank,
        })


@jwt_required
async def api_start_trial(request: web.Request):
    """Trial boshlash."""
    user_id = request["user_id"]
    success = await subscription_service.start_trial(user_id)
    return web.json_response({"success": success})


@jwt_required
async def api_delete_test(request: web.Request):
    """Testni o'chirish."""
    user_id = request["user_id"]
    test_id = int(request.match_info["test_id"])

    async with get_session() as session:
        test = await session.get(Test, test_id)
        if not test or test.user_id != user_id:
            return web.json_response({"error": "Test topilmadi"}, status=404)

        await session.delete(test)
        return web.json_response({"success": True})


# ============ Static fayllar (WebApp) ============

async def serve_webapp_index(request: web.Request):
    """WebApp index.html."""
    index_file = WEBAPP_DIR / "index.html"
    if index_file.exists():
        return web.FileResponse(index_file)
    return web.Response(text="QuizMaster WebApp - index.html topilmadi", status=404)


async def serve_static(request: web.Request):
    """CSS/JS fayllar."""
    path = request.match_info.get("path", "")
    file_path = WEBAPP_DIR / path

    if file_path.exists() and file_path.is_file():
        return web.FileResponse(file_path)
    return web.Response(text="Fayl topilmadi", status=404)


# ============ App setup ============

def create_app() -> web.Application:
    """Aiohttp app yaratish."""
    app = web.Application(client_max_size=25 * 1024 * 1024)  # 25 MB

    # CORS
    cors = cors_setup(app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })

    # API Routes
    api_routes = [
        web.get("/api/health", health),
        web.post("/api/auth/login", auth_login),
        web.get("/api/user", api_get_user),
        web.post("/api/upload", api_upload_file),
        web.post("/api/generate", api_generate_quiz),
        web.get("/api/tests", api_get_tests),
        web.get("/api/tests/{test_id}", api_get_test),
        web.post("/api/tests/{test_id}/submit", api_submit_test),
        web.post("/api/tests/{test_id}/share", api_share_test),
        web.delete("/api/tests/{test_id}", api_delete_test),
        web.get("/api/leaderboard", api_get_leaderboard),
        web.post("/api/trial", api_start_trial),
    ]

    for route in api_routes:
        resource = cors.add(app.router.add_resource(route.path))
        for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS"]:
            try:
                if route.method.upper() == method:
                    resource.add_route(method, route.handler)
            except Exception:
                pass

    # Static WebApp fayllar
    if WEBAPP_DIR.exists():
        app.router.add_get("/", serve_webapp_index)
        app.router.add_get("/app", serve_webapp_index)
        app.router.add_get("/{path:css/.*}", serve_static)
        app.router.add_get("/{path:js/.*}", serve_static)
        logger.info(f"WebApp static fayllar: {WEBAPP_DIR}")
    else:
        logger.warning(f"WebApp papkasi topilmadi: {WEBAPP_DIR}")

    return app


if __name__ == "__main__":
    import asyncio
    from bot.db.session import init_db

    async def run():
        await init_db()
        app = create_app()
        port = int(os.getenv("PORT", settings.api_port))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, settings.api_host, port)
        await site.start()
        print(f"API {port} portda ishlamoqda")
        await asyncio.sleep(float("inf"))

    asyncio.run(run())
