PIPELINE_PROGRESS={

"extraction":15,
"eligibility":30,
"validation":45,
"compliance":60,
"submission":80,
"clearinghouse":100

}

def assign_progress(
    event
):

    try:

        progress=int(
            float(
                event.get(
                    "progress",
                    0
                ) or 0
            )
        )

    except:

        progress=0


    stage=(
        event.get(
            "stage",
            ""
        )
        .strip()
        .lower()
    )

    status=(
        event.get(
            "status",
            ""
        )
        .strip()
        .upper()
    )


    if status=="COMPLETED":

        event["progress"]=PIPELINE_PROGRESS.get(
            stage,
            100
        )

    elif progress<=0:

        event["progress"]=PIPELINE_PROGRESS.get(
            stage,
            0
        )

    return event