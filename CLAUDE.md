## Adding a new strategy

When registering a new strategy in `backend/strategies/__init__.py`, also add
it to `STATIC_STRATEGIES` in `frontend/index.html`. That list is a hardcoded
snapshot (name + description) used to populate the strategy dropdown
instantly on page load, without waiting on a backend round trip — it is not
derived from the backend registry, so it goes stale silently if you forget.
A background fetch does refresh it a second or two after page load, but the
first paint will be missing the new strategy until this file is updated.
