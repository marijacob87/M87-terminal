def normalize_code_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [
        str(code).strip().upper()
        for code in value
        if str(code).strip()
    ]


def order_commands(commands: list[dict], saved_order) -> list[dict]:
    order = normalize_code_list(saved_order)
    if not order:
        return list(commands)
    positions = {code: index for index, code in enumerate(order)}
    indexed = list(enumerate(commands))
    indexed.sort(key=lambda pair: (
        positions.get(
            str(pair[1].get("code", "")).strip().upper(),
            len(positions) + pair[0],
        ),
        pair[0],
    ))
    return [command for _index, command in indexed]
