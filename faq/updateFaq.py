import os ,requests, json5, sys
from datetime import datetime
from dotenv import load_dotenv

START = datetime.now()
load_dotenv()

HEADERS = {"Authorization": f"Bot {os.environ['DISCORD_TOKEN']}","Content-Type": "application/json"}
FAQ_CHANNEL = "1448400987093205004"
BASE_ENDPOINT = "https://discord.com/api/v10/"

print(repr(os.environ['DISCORD_TOKEN']))

def sendMessage(message):
    chunks = []
    limit = 2000
    while len(message) > limit:
        split = message.rfind('\n', 0, limit)
        if split == -1:
            split = limit
        chunks.append(message[:split])
        message = message[split+1:]
    chunks.append(message)

    sentMessageIDs = []
    for chunk in chunks:
        r = requests.post(
            f"{BASE_ENDPOINT}channels/{FAQ_CHANNEL}/messages",            
            headers=HEADERS,
            json={"content": chunk}
        )
        if r.status_code != 200:
            print(f"Failed to send message: {r.status_code} - {r.text}")
            r.raise_for_status() 
        sentMessageIDs.append(r.json()["id"])
    return sentMessageIDs

def deleteMessage(messageID):
    r = requests.delete(
        f"{BASE_ENDPOINT}channels/{FAQ_CHANNEL}/messages/{messageID}",
        headers=HEADERS
    )
    if r.status_code not in (204, 404):  # 404 = already deleted, fine to ignore
        print(f"Failed to delete {messageID}: {r.status_code} {r.text}")

if __name__ == "__main__":
    print("Loading Files...")
    with open('faq/oldMessageIDs.jsonc') as f:
        oldMessageIDs = json5.load(f)
    with open('faq/faq.md', encoding='utf-8') as f: 
        faqContent = f.read()

    if not faqContent:
        print("No FAQ found. Exiting...")
        sys.exit()
    
    # delete old faq
    if oldMessageIDs :
        print("Deleting old FAQ messages...")
        for oldMessageID in oldMessageIDs:
            deleteMessage(oldMessageID)
    # send new faq
    print("Sending new FAQ messages...")
    newMessageIDs = sendMessage(faqContent)

    #store new ids
    with open('faq/oldMessageIDs.jsonc', 'w') as f:
        json5.dump(newMessageIDs, f, quote_keys=True)
    
