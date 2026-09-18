import redis
import dotenv
dotenv.load_dotenv()
LACLAUGPT_REDIS_URL = dotenv.get_key(dotenv.find_dotenv(), "LACLAUGPT_REDIS_URL")

r = redis.from_url(LACLAUGPT_REDIS_URL)
print(r.ping())
