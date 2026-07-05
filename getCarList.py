import requests, json, time, re, base64,io,os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from dotenv import load_dotenv
load_dotenv()

HEADERS = {"Authorization": f"Bot {os.environ['DISCORD_TOKEN']}"}
FORUM_CHANNEL_ID = "1449430957663719653"
GUILD_ID = "1448022502969315440"
TAGS_DICT = {
    "1449431169106972843": "Japanese",
    "1449431279262236812": "Asian",
    "1450861039628587088": "NPC Car",
    "1449431191433379861": "European",
    "1449431207971520572": "American"
}
THUMBNAIL_RES = [314,160]
YEAR_RANGE_REGEX = r'^\d{4}[-–—―]\d{4}'
existingImages = {}

def getThreads():
    print("Fetching data from discord")
    threads = []
    
    r = requests.get(
        f"https://discord.com/api/v10/guilds/{GUILD_ID}/threads/active",
        headers=HEADERS
    ).json()
    active = [t for t in r.get("threads", []) if t["parent_id"] == FORUM_CHANNEL_ID]
    threads += active
    
    # Archived threads (paginated)
    before = None
    while True:
        url = f"https://discord.com/api/v9/channels/{FORUM_CHANNEL_ID}/threads/archived/public?limit=100"
        if before:
            url += f"&before={before}"
        r = requests.get(url, headers=HEADERS).json()
        batch = r.get("threads", [])
        if not batch:
            break
        threads += batch
        if not r.get("has_more"):
            break
        before = batch[-1]["thread_metadata"]["archive_timestamp"]
        time.sleep(0.5)

    print(f"{len(threads)} threads have been found.")
    return threads

def processThreadName(name: str, reactionCount:str):
    name: str = name.strip()

    # Get the years (1990-1997)
    years: re.Match = re.search(YEAR_RANGE_REGEX,name)
    if not years:
        return
    yearsMin: str = years[0][0:4]
    yearsMax: str = years[0][5:9]
    name: str = name.replace(years[0],"").strip()


    # Get the Chassis code
    chassis: re.Match = re.search(r'\[(.{0,})\]$',name)
    if chassis:
        name: str = name.replace(chassis.group(0),"").strip()


    # separate cars into list
    cars: list = name.split("/")

    # divide by how many cars there is
    yearDiff = int(yearsMax)-int(yearsMin)
    reactionCountPerYear = 0
    if not yearDiff <= 0:
        reactionCountPerYear = (int(reactionCount) / yearDiff) / len(cars)
    else:
        reactionCountPerYear = (int(reactionCount) / len(cars))


    fullCars: list = []
    for car in cars:
        car: str = car.strip()
        brand: str = re.search(r'^\S{0,}',car).group(0)
        model: str = car.replace(brand,"").strip()
        fullCar: dict = {
            'brand': brand,
            'model': model,
            'yearsMin' : yearsMin,
            'yearsMax' : yearsMax,
            'chassis' : chassis.group(1) if chassis else '',
            'reactionCountPerYear' : reactionCountPerYear or 0
        }
        fullCars.append(fullCar)
    return fullCars

def getFirstMsg(thread_id):
    r = requests.get(
        f"https://discord.com/api/v10/channels/{thread_id}/messages/{thread_id}",
        headers=HEADERS
    )
    return r.json() if r.status_code == 200 else None



def downloadImage(url):
    r = requests.get(f"{url}&width={THUMBNAIL_RES[0]}&height={THUMBNAIL_RES[1]}")
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=40)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()

def fetchThreadData(thread):
        msg = getFirstMsg(thread["id"])
        img = existingImages.get(thread["id"])  # use cached if exists
        if img is None and msg:
            attachments = msg.get("attachments", [])
            if attachments:
                img = downloadImage(attachments[0]["proxy_url"])
        return thread["id"], msg, img


def processThreads():
    threads = getThreads()
    validThreads = 0
    threadsCount = 0
    carList = []
    carCount = 0
    errors = []
    # Load existing image cache
    if os.path.exists("carList.json"):
        with open("carList.json", "r", encoding="utf-8") as f:
            existing = json.load(f)
            existingImages = existing.get("images", {})

    # Fetch all needed data
    print("Fetching messages and images...")
    msgMap = {}
    imgMap = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetchThreadData, t): t["id"] for t in threads}
        for future in as_completed(futures):
            thread_id, msg, img = future.result()
            msgMap[thread_id] = msg
            imgMap[thread_id] = img
    

    print("Processing threads...")
    for t in threads:
        threadsCount += 1

        if t['id'] == "1450407132959866913":
            continue # Skip over "Posting guidelines" pinned thread
        if not re.match(YEAR_RANGE_REGEX,t['name']):
            errors.append(f"Error: the thread '{t['name']}' is incorrectly formatted.")
            continue
        if len(t['name'].split()) < 3:
            errors.append(f"Error: the thread '{t['name']}' is incorrectly formatted.")
            continue
        msg = msgMap.get(t["id"])

        # Highest reaction count across all emojis
        reactionCount = 0
        if msg:
            reactions = msg.get("reactions", [])
            if reactions:
                reactionCount = max(r["count"] for r in reactions)
        # Process tags

        tags = []
        for tag in t["applied_tags"]:
            tags.append([TAGS_DICT[tag],tag])
        # Process thread name
        cars: list = processThreadName(t['name'],reactionCount)
        if not cars:
            continue
        
        for car in cars:
            carData = {
                "id":carCount,
                "url": t['id'],
                "reactionCount": reactionCount,
                "tags": tags,
                "rebadge": True if len(cars) > 1 else False,
                "createdAt":t["thread_metadata"]["create_timestamp"]
            }
            carData.update(car)
            carList.append(carData)
            carCount +=1
        #time.sleep(0.15)
        validThreads += 1

    export = {
        "totalCars":validThreads,
        "totalCarsRebadge": carCount,
        "exportDate": datetime.now().isoformat(),
        "cars" : carList,
        "images": imgMap
    }

    with open("carList.json", "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    print("========================\n Exporting Finished\n========================\nStats:")
    print(f"\n{carCount} Cars Exported")
    if errors:
        print(*errors, sep='\n')

if __name__ == "__main__":
    processThreads()

