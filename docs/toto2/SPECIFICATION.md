# Specification

The provider protocol is schema version 2. Input history is a list of exact position-name mappings.
Draw-sequence timestamps must be integer, unique, increasing, and gap-free. Calendar timestamps must
be strictly increasing datetimes. Context length is bounded to 512 because 512 is the formally
recorded runtime context; horizons 2 and 5 remain contract-enabled but require later real-runtime
certification.

Native output has exact shape `[9, 1, series, horizon]`. The adapter removes only the singleton
batch dimension and stores every quantile as `[series, horizon]`. It performs no lottery-domain
rounding or constrained projection in P0-P2.
