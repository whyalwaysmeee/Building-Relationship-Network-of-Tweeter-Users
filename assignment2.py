import twitter
import sys
import time
from urllib.error import URLError
from http.client import BadStatusLine
from functools import partial
from sys import maxsize as maxint
import networkx as nx
import matplotlib.pyplot as plt


# API key:                hVnhVyEYPQnAR4Nl6BMMvs23r
# API secret key:         uV1qgA1wolDX3r2G1kbvhzmfiulNDbmyfQ1d5YIlxxMs7uX3WU
# access token:           1120096820586274816-MmQt4LLG3n8C5Gfeyp96H4IPC5crp7
# access token secret:    dJVkoDrr8iSJcIObedSIpfQ2sV2paodC1KaouukzkQ3Og

def oauth_login():
    # XXX: Go to http://twitter.com/apps/new to create an app and get values
    # for these credentials that you'll need to provide in place of these
    # empty string values that are defined as placeholders.
    # See https://developer.twitter.com/en/docs/basics/authentication/overview/oauth
    # for more information on Twitter's OAuth implementation.

    CONSUMER_KEY = 'hVnhVyEYPQnAR4Nl6BMMvs23r'
    CONSUMER_SECRET = 'uV1qgA1wolDX3r2G1kbvhzmfiulNDbmyfQ1d5YIlxxMs7uX3WU'
    OAUTH_TOKEN = '1120096820586274816-MmQt4LLG3n8C5Gfeyp96H4IPC5crp7'
    OAUTH_TOKEN_SECRET = 'dJVkoDrr8iSJcIObedSIpfQ2sV2paodC1KaouukzkQ3Og'

    auth = twitter.oauth.OAuth(OAUTH_TOKEN, OAUTH_TOKEN_SECRET,
                               CONSUMER_KEY, CONSUMER_SECRET)

    twitter_api = twitter.Twitter(auth=auth)
    return twitter_api

def make_twitter_request(twitter_api_func, max_errors=10, *args, **kw):
    # A nested helper function that handles common HTTPErrors. Return an updated
    # value for wait_period if the problem is a 500 level error. Block until the
    # rate limit is reset if it's a rate limiting issue (429 error). Returns None
    # for 401 and 404 errors, which requires special handling by the caller.
    def handle_twitter_http_error(e, wait_period=2, sleep_when_rate_limited=True):

        if wait_period > 3600:  # Seconds
            print('Too many retries. Quitting.', file=sys.stderr)
            raise e

        # See https://developer.twitter.com/en/docs/basics/response-codes
        # for common codes

        if e.e.code == 401:
            print('Encountered 401 Error (Not Authorized)', file=sys.stderr)
            return None
        elif e.e.code == 404:
            print('Encountered 404 Error (Not Found)', file=sys.stderr)
            return None
        elif e.e.code == 429:
            print('Encountered 429 Error (Rate Limit Exceeded)', file=sys.stderr)
            if sleep_when_rate_limited:
                print("Retrying in 15 minutes...ZzZ...", file=sys.stderr)
                sys.stderr.flush()
                time.sleep(60 * 15 + 5)
                print('...ZzZ...Awake now and trying again.', file=sys.stderr)
                return 2
            else:
                raise e  # Caller must handle the rate limiting issue
        elif e.e.code in (500, 502, 503, 504):
            print('Encountered {0} Error. Retrying in {1} seconds'.format(e.e.code, wait_period), file=sys.stderr)
            time.sleep(wait_period)
            wait_period *= 1.5
            return wait_period
        else:
            raise e

    # End of nested helper function

    wait_period = 2
    error_count = 0

    while True:
        try:
            return twitter_api_func(*args, **kw)
        except twitter.api.TwitterHTTPError as e:
            error_count = 0
            wait_period = handle_twitter_http_error(e, wait_period)
            if wait_period is None:
                return
        except URLError as e:
            error_count += 1
            time.sleep(wait_period)
            wait_period *= 1.5
            print("URLError encountered. Continuing.", file=sys.stderr)
            if error_count > max_errors:
                print("Too many consecutive errors...bailing out.", file=sys.stderr)
                raise
        except BadStatusLine as e:
            error_count += 1
            time.sleep(wait_period)
            wait_period *= 1.5
            print("BadStatusLine encountered. Continuing.", file=sys.stderr)
            if error_count > max_errors:
                print("Too many consecutive errors...bailing out.", file=sys.stderr)
                raise

def get_user_profile(twitter_api, screen_names=None, user_ids=None):
    # Must have either screen_name or user_id (logical xor)
    assert (screen_names != None) != (user_ids != None), "Must have screen_names or user_ids, but not both"

    items_to_info = {}

    items = screen_names or user_ids

    while len(items) > 0:

        # Process 100 items at a time per the API specifications for /users/lookup.
        # See http://bit.ly/2Gcjfzr for details.

        items_str = ','.join([str(item) for item in items[:100]])
        items = items[100:]

        if screen_names:
            response = make_twitter_request(twitter_api.users.lookup,
                                            screen_name=items_str)
        else:  # user_ids
            response = make_twitter_request(twitter_api.users.lookup,
                                            user_id=items_str)

        for user_info in response:
            if screen_names:
                items_to_info[user_info['screen_name']] = user_info
            else:  # user_ids
                items_to_info[user_info['id']] = user_info

    return items_to_info

def get_friends_followers_ids(twitter_api, screen_name=None, user_id=None,
                              friends_limit=maxint, followers_limit=maxint):
    # Must have either screen_name or user_id (logical xor)
    assert (screen_name != None) != (user_id != None), "Must have screen_name or user_id, but not both"

    # See http://bit.ly/2GcjKJP and http://bit.ly/2rFz90N for details
    # on API parameters

    get_friends_ids = partial(make_twitter_request, twitter_api.friends.ids,
                              count=5000)
    get_followers_ids = partial(make_twitter_request, twitter_api.followers.ids,
                                count=5000)

    friends_ids, followers_ids = [], []

    for twitter_api_func, limit, ids, label in [
        [get_friends_ids, friends_limit, friends_ids, "friends"],
        [get_followers_ids, followers_limit, followers_ids, "followers"]
    ]:

        if limit == 0: continue

        cursor = -1
        while cursor != 0:

            # Use make_twitter_request via the partially bound callable...
            if screen_name:
                response = twitter_api_func(screen_name=screen_name, cursor=cursor)
            else:  # user_id
                response = twitter_api_func(user_id=user_id, cursor=cursor)

            if response is not None:
                ids += response['ids']
                cursor = response['next_cursor']

            print('Fetched {0} total {1} ids for {2}'.format(len(ids), label, (user_id or screen_name)),
                  file=sys.stderr)

            # XXX: You may want to store data during each iteration to provide an
            # an additional layer of protection from exceptional circumstances

            if len(ids) >= limit or response is None:
                break

    # Do something useful with the IDs, like store them to disk...
    return friends_ids[:friends_limit], followers_ids[:followers_limit]

# given a list of a user's friends' ids and followers' ids, return his 5 most popular reciprocal friends
def get_5_most_popular_reciprocal_friends(twitter_api, friends_ids, followers_ids):
    reciprocal_friends = set(friends_ids) & set(followers_ids)

    temp = list(reciprocal_friends)

    followers_popularity = []

    # get users' profile
    user_profiles = get_user_profile(twitter_api, user_ids=list(reciprocal_friends))

    # get user's numbers of followers
    for i in reciprocal_friends:
        followers_popularity.append(user_profiles[i]['followers_count'])

    five_most_popular_friends = []

    # a user may have more than or equal to or less than 5 reciprocal friends
    if (len(reciprocal_friends) >= 5):
        for i in range(5):
            max_index = followers_popularity.index(max(followers_popularity))
            five_most_popular_friends.append(temp[max_index])
            followers_popularity[max_index] = -1
    else:
        for i in range(len(reciprocal_friends)):
            max_index = followers_popularity.index(max(followers_popularity))
            five_most_popular_friends.append(temp[max_index])
            followers_popularity[max_index] = -1

    return five_most_popular_friends

def crawl_followers(twitter_api, screen_name, limit):
    # Resolve the ID for screen_name and start working with IDs for consistency
    # in storage

    seed_id = str(twitter_api.users.show(screen_name=screen_name)['id'])
    friends_ids, followers_ids = get_friends_followers_ids(twitter_api, user_id=seed_id,
                                                           friends_limit=6000, followers_limit=limit)

    # get the user's five most popular reciprocal friends
    five_most_popular_friends = get_5_most_popular_reciprocal_friends(twitter_api, friends_ids, followers_ids)

    # this list is used to record the users' ids in each iteration
    next_queue = five_most_popular_friends

    # this dictionary is used to store the final output
    friend_dictionary = {}
    friend_dictionary[seed_id] = five_most_popular_friends

    # this list is used to record the number of users that have been crawled
    count = [seed_id]
    count.extend(five_most_popular_friends)

    # here depth is not set because we are not sure what it is.
    # I stop the program when the total number of users is greater than 100
    while len(count) < 100:
        print(len(count), "users have been crawled")
        (queue, next_queue) = (next_queue, [])
        for fid in queue:
            friends_ids, follower_ids = get_friends_followers_ids(twitter_api, user_id=fid,
                                                                  friends_limit=6000,
                                                                  followers_limit=limit)

            five_most_popular_friends = get_5_most_popular_reciprocal_friends(twitter_api,friends_ids, followers_ids)

            friend_dictionary[fid] = five_most_popular_friends

            for i in five_most_popular_friends:
                if i not in count:
                    count.append(i)
                    next_queue.append(i)

    return friend_dictionary

# main function
twitter_api = oauth_login()
screen_name = "DezBryant"

result = crawl_followers(twitter_api, screen_name, 15000)

print(result)
print(len(result))

# this txt file is used to store the result
f = open("friends_dictionary.txt", "w")
for key in result:
    f.write(str(key))
    f.write("\n")
    f.write(str(result[key]))
    f.write("\n")
f.close()

# add nodes and edges to the graph
Network = nx.Graph()
for key in result:
    Network.add_node(key)
    if len(result[key]) != 0:
        for friend_id in result[key]:
            Network.add_node(friend_id)
for key in result:
    if len(result[key]) != 0:
        for friend_id in result[key]:
            Network.add_edge(key, friend_id)

# draw the network, store the graph as png file and show the graph
nx.draw(Network)
plt.savefig("Network.png")
plt.show()

# print the number of nodes and edges, diameter and average distance of the network
print("The number of nodes is: ")
print(nx.number_of_nodes(Network))
print("The number of edges is: ")
print(nx.number_of_edges(Network))
print("The diameter is: ")
print(nx.diameter(Network))
print("The average distance of the graph is: ")
print(nx.average_shortest_path_length(Network))

# this txt file is used to store the number of nodes and edges, diameter and average distance information
f1 = open("stats.txt", "w")
f1.write("The number of nodes is: ")
f1.write(str(nx.number_of_nodes(Network)))
f1.write("\nThe number of edges is: ")
f1.write(str(nx.number_of_edges(Network)))
f1.write("\nThe diameter is: ")
f1.write(str(nx.diameter(Network)))
f1.write("\nThe average distance of the graph is: ")
f1.write(str(nx.average_shortest_path_length(Network)))
f1.close()










