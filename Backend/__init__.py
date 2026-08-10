"""Things the app does that are neither a route nor a query.

A route handles HTTP. A repository handles SQL. Talking to a third-party API is
neither, and putting it in either place is how a signup handler ends up owning
retry logic.
"""
