import concurrent.futures
import time
import requests

url = "http://localhost:8000/time"
start_time = time.time()

def hit(i):
    try:
        response = requests.get(url)
        print(f"{i}: {response.json()}")
    except Exception as e:
        print("failed to get time")
        raise e


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        for _ in executor.map(hit, range(100)):
            ...

main()
print(f"Took {time.time() - start_time}")