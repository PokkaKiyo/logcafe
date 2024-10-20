import arrow


def curr_time() -> str:
    return arrow.now().format("YYYY-MM-DDTHH:mm:ssZZ")
