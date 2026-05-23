def calcular_sm2(
    repetitions,
    interval,
    ease,
    quality
):

    if quality < 3:
        repetitions = 0
        interval = 1
        ease = max(1.3, ease - 0.2)

        return repetitions, interval, ease

    repetitions += 1

    if repetitions == 1:
        interval = 1

    elif repetitions == 2:
        interval = 6

    else:
        interval = round(interval * ease)

    ease = ease + (
        0.1 - (5 - quality) * (
            0.08 + (5 - quality) * 0.02
        )
    )

    ease = max(1.3, ease)

    return repetitions, interval, ease