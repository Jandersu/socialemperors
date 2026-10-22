from sessions import session, neighbor_session, neighbors, save_session
from engine import timestamp_now
from tutorial import prepare_tutorial

def get_player_info(USERID):
    # Update last logged in
    ts_now = timestamp_now()
    session(USERID)["playerInfo"]["last_logged_in"] = ts_now
    # Resume only after the caller has recovered pending writes under its lock.
    # Old unfinished saves may already have consumed the tutorial's tree.
    if prepare_tutorial(session(USERID)):
        save_session(USERID)
    # player
    player_info = {
        "result": "ok",
        "processed_errors": 0,
        "timestamp": ts_now,
        "playerInfo": session(USERID)["playerInfo"],
        "map": session(USERID)["maps"][0],
        "privateState": session(USERID)["privateState"],
        "neighbors": neighbors(USERID)
    }
    return player_info

def get_neighbor_info(userid, map_number):
    neighbor_info = {
        "result": "ok",
        "processed_errors": 0,
        "timestamp": timestamp_now(),
        "playerInfo": neighbor_session(userid)["playerInfo"],
        "map": neighbor_session(userid)["maps"][map_number],
        "privateState": neighbor_session(userid)["privateState"],
        "neighbors": neighbors(userid)
    }
    return neighbor_info
