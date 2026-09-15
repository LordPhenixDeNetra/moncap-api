from __future__ import annotations
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from app.main import create_app, _construire_cors_origins
from app.core.settings import get_settings

settings = get_settings()
origins = _construire_cors_origins(settings)
print('======== CORS allow_origins ========')
for o in origins:
    has_star = '*' in o
    print('  ' + str(o) + '  (' + ('ERREUR' if has_star else 'OK') + ')')
print('Total origines = ' + str(len(origins)))
stars = [o for o in origins if '*' in o]
assert len(stars) == 0, 'ERREUR origines contiennent *'
print('OK: Aucune origine contient "*" (safe Bearer JWT)\n')

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    app = create_app()
    print('OK FastAPI app created OK, lifespan registered')
    print('Routes count: ' + str(len(app.routes)) + '\n')

print('======== Middlewares enregistres ========')
i = 0
for mw in app.user_middleware:
    i += 1
    cls_name = getattr(mw.cls, '__name__', str(mw.cls))
    print('  #' + str(i) + ': ' + cls_name)
    if cls_name == 'CORSMiddleware':
        kwargs = mw.kwargs or {}
        print('       allow_credentials = ' + str(kwargs.get('allow_credentials')))
        print('       allow_methods      = ' + str(kwargs.get('allow_methods')))
        ah = kwargs.get('allow_headers') or []
        print('       allow_headers (count ' + str(len(ah)) + ')  = ' + str(ah))
        has_auth = 'authorization' in [h.lower() for h in ah]
        print('       allow_headers contient Authorization: ' + ('OUI !' if has_auth else 'NON (ERREUR !)'))
        assert has_auth, 'Authorization DOIT etre dans allow_headers'
        print('       expose_headers     = ' + str(kwargs.get('expose_headers')))
        print('       max_age            = ' + str(kwargs.get('max_age')) + 's')
        ao = kwargs.get('allow_origins') or []
        print('       allow_origins (count ' + str(len(ao)) + ') OK')
        stars_mw = [o for o in ao if '*' in o]
        assert len(stars_mw) == 0, 'allow_origins contient * dans middleware'
        print('       allow_origin_regex = ' + str(kwargs.get('allow_origin_regex')))
        print()

class FakeSettings:
    cors_allow_origins = ['*', 'https://moncap.innovamind.tech']
fake = FakeSettings()
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    out = _construire_cors_origins(fake)
    print('======== Test anti "*" ========')
    print('  Input: ["*", "https://moncap.innovamind.tech"]')
    print('  Output filtre: ' + str(out))
    assert '*' not in out, '* aurait du etre supprime'
    print('  OK Warnings emis: ' + str(len(w)))
    print('  OK "*" bien supprime de la liste (safe)\n')

print('TOUS CHECKS CORS CONFIG OK.')
