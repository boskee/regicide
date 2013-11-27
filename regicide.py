import requests
import hashlib
import json
import random
import sys

class ApiItemAmount(object):
    def __new__(self, item_type, amount):
        return {"type": item_type, "amount": amount}

class SagaAPI(object):
    secret = ""
    episodeLengths = {}
    apiUrl = ""
    clientApi = ""

    unlockLevelItemId = -1
    unlockLevelImage = ""
    debug = True

    def __init__(self, session, userId):
        self.session = session
        self.userId = userId

    def api_get(self, method, params):
        response = requests.get(self.apiUrl + "/" + method, params=params)
        if self.debug:
            print self.apiUrl + "/" + method + "\n"
            print "===============================\n"
            print response.text
            print "\n"
        return response

    def hand_out_winnings(self, item_type, amount):
        item = [
            ApiItemAmount(item_type, amount)
        ]
        params = {
            "_session": self.session,
            "arg0": json.dumps(item),
            "arg1": 1,
            "arg2": 1,
            "arg3": "hash",
        }
        return self.api_get("handOutItemWinnings", params)
 
    # gets the balance of all the items that the player has
    def get_balance(self):
        params = {"_session": self.session}
        return self.api_get("getBalance", params)

    def get_gameInitLight(self):
        params = {"_session": self.session}
        return self.api_get("gameInitLight", params)
           
    # full list with level details
    def get_gameInit(self):
        params = {"_session": self.session}
        return self.api_get("gameInit", params)

    def add_life(self):
        params = {"_session": self.session}
        return self.api_get("addLife", params)
 
    def is_level_unlocked(self, episode, level):
        params = {"_session": self.session, "arg0": episode, "arg1": level}
        response = self.api_get("isLevelUnlocked", params)
        return response.text == "true"
 
    def poll_episodeChampions(self, episode):
        params = {"_session": self.session, "arg0": episode}
        return self.api_get("getEpisodeChampions", params)

    def poll_levelScores(self, episode, level):
        params = {"_session": self.session, "arg0": episode, "arg1": level}
        return self.api_get("getLevelToplist", params)

    def post_unlockLevel(self, episode, level):
        params = {"_session": self.session}
        placement = "Map,%s,%s" % (episode, level)
        payload = [{
            "method": "ProductApi.purchase",
            "id": 0,
            "params": [{
                "imageUrl": self.unlockLevelImage,
                "orderItems": [{
                    "productPackageType": self.unlockLevelItemId,
                    "receiverCoreUserId": self.userId
                }],
                "placement": placement,
                "title": "Level Unlock",
                "description": "Buy your way to the next level.",
                "currency": "KHC"
            }]
        }]
       
        unlockAttempt = requests.post(self.clientApi, verify=False, params=params, data=json.dumps(payload)).json()
        if self.debug:
            print json.dumps(unlockAttempt, sort_keys = False, indent = 4)

        return unlockAttempt[0]["result"]["status"] == "ok"

    def start_game(self, episode, level):
        params = {"_session": self.session, "arg0": episode, "arg1": level}
        return self.api_get("gameStart", params).json()["seed"]

    def end_game(self, episode, level, seed, score=None):
        if score is None:
            score = random.randrange(3000, 6000) * 100
        dic = {
            "timeLeftPercent": -1,
            "episodeId": episode,
            "levelId": level,
            "score": score,
            "variant": 0,
            "seed": seed,
            "reason": 0,
            "userId": self.userId,
            "secret": self.secret
        }
        dic["cs"] = hashlib.md5("%(episodeId)s:%(levelId)s:%(score)s:%(timeLeftPercent)s:%(userId)s:%(seed)s:%(secret)s" % dic).hexdigest()[:6]

        params = {"_session": self.session, "arg0": json.dumps(dic)}
        return self.api_get("gameEnd", params)

    def print_scores(self, episode, level):
        scores = self.poll_levelScores(episode, level).json()
        print json.dumps(scores.values()[0][0], sort_keys = False, indent = 4)
        print json.dumps(scores.values()[0][1], sort_keys = False, indent = 4)
        print json.dumps(scores.values()[0][2], sort_keys = False, indent = 4)
   
    def print_status(self):
        print json.dumps(self.poll_status().json(), sort_keys = False, indent = 4)

    def complete_level(self, level):
        targetEpisode, targetLevel = self.get_episode_level(level)

        is_unlocked = self.is_level_unlocked(targetEpisode, targetLevel)
        if not is_unlocked:
            self.complete_level(level - 1)
        
        response = self.play_game(targetEpisode, targetLevel).json()

        if response["episodeId"] == -1:
            needUnlock = False
            for event in response["events"]:
                if event["type"] == "LEVEL_LOCKED":
                    needUnlock = True
                    break

            if needUnlock:
                self.post_unlockLevel(targetEpisode, targetLevel)
                self.complete_level(level)

        print "Beat episode {0} level {1}".format(targetEpisode, targetLevel)

    def get_episode_level(self, level):
        if len(self.episodeLengths) == 0:
            response = self.get_gameInit()
            episodeDescriptions = response.json()["universeDescription"]["episodeDescriptions"]
            for episode in episodeDescriptions:
                self.episodeLengths[episode["episodeId"]] = len(episode["levelDescriptions"])

        targetEpisode = -1
        targetLevel = level
        currentEpisode = 1

        while targetEpisode == -1:
            if targetLevel > self.episodeLengths[currentEpisode]:
                targetLevel = targetLevel - self.episodeLengths[currentEpisode]
                currentEpisode = currentEpisode + 1
            else:
                targetEpisode = currentEpisode
                break

        return targetEpisode, targetLevel
           
    def play_gameAutoScore(self, episode, level, starProgressions=None):
        if starProgressions is not None:
            minPoints = starProgressions["universeDescription"]["episodeDescriptions"][episode-1]["levelDescriptions"][level-1]["starProgressions"][2]["points"]
            randomScore = 1
            while (randomScore % 2 != 0):
                # generate a random number at most 50000 points over the min 3 star and keep trying until it is even
                randomScore = random.randrange(minPoints/10, minPoints/10+5000)
            myScore = randomScore * 10
            # print "Score: %s out of %s" % (myScore, minPoints)
        else:
            # revert to pulling the top scores. This probably won't work if none of your friends have made it to that level
            scoreList = self.poll_levelScores(episode, level).json()
            # take the top score and add 5000 points
            myScore = scoreList.values()[0][0]["value"] + 5000

        return self.play_game(episode, level, myScore)

    def play_gameLoop(self, episode, level):
        # create a JSON file full of tons and tons of data but only call it once since it is so large
        starProgressions = self.get_gameInit().json()
       
        while True:
            try:
                result = self.play_gameAutoScore(episode, level, starProgressions).json()
               
                try:
                    # This is not quite right but it works since LEVEL_GOLD_REWARD still has a episodeId and levelId like LEVEL_UNLOCKED
                    # This only beats new levels that reported back the new unlocked level
                    data = json.loads(result["events"][0].values()[2])
                    data["episodeId"]
                    data["levelId"]
                    level = level + 1
                except KeyError:
                    print "Next level wasn't reported, Trying to unlock episode %s..." % (episode+1)
                    self.post_unlockLevel(episode, level-1)
                    episode = episode + 1
                    level = 1
                except:
                    print sys.exc_info()[0]
                    break
            except IndexError:
                print "Next level wasn't reported, Trying to unlock episode %s..." % (episode+1)
                self.post_unlockLevel(episode, level-1)
                episode = episode + 1
                level = 1
            except:
                print sys.exc_info()[0]
                break

    def play_game(self, episode, level, score=None):
        seed = self.start_game(episode, level)
        return self.end_game(episode, level, seed, score)