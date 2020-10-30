import pytest
import gitlab
import urllib
from datetime import datetime
from unittest import mock
from sqlalchemy.orm import joinedload
from _pytest.monkeypatch import MonkeyPatch

from meltano.core.project import Project, PROJECT_READONLY_ENV
from meltano.core.project_settings_service import ProjectSettingsService
from meltano.api.security import FreeUser, users
from meltano.api.security.oauth import gitlab_token_identity, OAuthError
from meltano.api.models.security import db, User
from meltano.api.models.oauth import OAuth
from meltano.api.models.embed_token import EmbedToken, ResourceType

from flask import url_for
from flask_login import current_user
from flask_security import login_user, logout_user, AnonymousUser
from freezegun import freeze_time


def gitlab_client():
    client_mock = mock.Mock()
    client_mock.auth.return_value = None
    user = mock.Mock(username="gitlabfan", email="valid@test.com", state="active", id=1)

    type(client_mock).user = mock.PropertyMock(return_value=user)

    return client_mock


class TestFreeUser:
    def test_all_roles(self):
        assert len(FreeUser().roles) == 2

        role = users.find_or_create_role("this_is_a_test")

        assert FreeUser().has_role(role)


@pytest.mark.usefixtures("seed_users")
class TestNothingEnabled:
    @pytest.fixture(scope="class")
    def app(self, create_app):
        return create_app()

    def test_current_user(self, app):
        with app.test_request_context("/"):
            assert isinstance(current_user._get_current_object(), FreeUser)

    def test_identity(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("api_root.identity"))

            assert res.status_code == 200
            assert res.json["anonymous"] == True
            assert res.json["can_sign_in"] == False

    def test_bootstrap(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("root.bootstrap"))

            assert res.status_code == 302
            assert res.location == url_for("root.default", _external=True)

    def test_upgrade(self, app, api):
        with app.test_request_context():
            res = api.post(url_for("api_root.upgrade"))

            assert res.status_code == 201
            assert res.data == b"Meltano update in progress."

    def test_plugins(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("plugins.all"))

            assert res.status_code == 200
            assert "extractors" in res.json

    def test_plugins_add(self, app, api):
        with app.test_request_context():
            res = api.post(
                url_for("plugins.add"),
                json={"plugin_type": "extractors", "name": "tap-gitlab"},
            )

            assert res.status_code == 200
            assert res.json["name"] == "tap-gitlab"


@pytest.mark.usefixtures("seed_users")
class TestProjectReadonlyEnabled:
    @pytest.fixture(scope="class")
    def project(self, project):
        Project.deactivate()

        monkeypatch = MonkeyPatch()
        monkeypatch.setenv(PROJECT_READONLY_ENV, "true")

        yield project

        monkeypatch.undo()

    def test_current_user(self, app):
        with app.test_request_context("/"):
            assert isinstance(current_user._get_current_object(), FreeUser)

    def test_identity(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("api_root.identity"))

            assert res.status_code == 200
            assert res.json["anonymous"] == True
            assert res.json["can_sign_in"] == False

    def test_bootstrap(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("root.bootstrap"))

            assert res.status_code == 302
            assert res.location == url_for("root.default", _external=True)

    def test_upgrade(self, app, api):
        with app.test_request_context():
            res = api.post(url_for("api_root.upgrade"))

            assert res.status_code == 201
            assert res.data == b"Meltano update in progress."

    def test_plugins(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("plugins.all"))

            assert res.status_code == 200
            assert "extractors" in res.json

    def test_plugins_add(self, app, api):
        with app.test_request_context():
            res = api.post(
                url_for("plugins.add"),
                json={"plugin_type": "extractors", "name": "tap-gitlab"},
            )

            assert res.status_code == 499
            assert b"deployed as read-only" in res.data

    def test_pipeline_schedules_save(
        self, app, api, tap, target, plugin_discovery_service
    ):
        with app.test_request_context():
            with mock.patch(
                "meltano.core.schedule_service.PluginDiscoveryService",
                return_value=plugin_discovery_service,
            ):
                res = api.post(
                    url_for("orchestrations.save_pipeline_schedule"),
                    json={
                        "name": "mock-to-mock",
                        "extractor": "tap-mock",
                        "loader": "target-mock",
                        "transform": "skip",
                        "interval": "@once",
                    },
                )

                assert res.status_code == 499
                assert b"deployed as read-only" in res.data

    def test_dashboards_save(self, app, api):
        with app.test_request_context():
            res = api.post(
                url_for("dashboards.save_dashboard"),
                json={"name": "test-dashboard", "description": ""},
            )

            assert res.status_code == 499
            assert b"deployed as read-only" in res.data


@pytest.mark.usefixtures("seed_users")
class TestReadonlyEnabled:
    @pytest.fixture(scope="class")
    def app(self, create_app):
        monkeypatch = MonkeyPatch()
        monkeypatch.setitem(ProjectSettingsService.config_override, "ui.readonly", True)

        yield create_app()

        monkeypatch.undo()

    def test_current_user(self, app):
        with app.test_request_context("/"):
            assert isinstance(current_user._get_current_object(), FreeUser)

    def test_identity(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("api_root.identity"))

            assert res.status_code == 200
            assert res.json["anonymous"] == True
            assert res.json["can_sign_in"] == False

    def test_bootstrap(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("root.bootstrap"))

            assert res.status_code == 302
            assert res.location == url_for("root.default", _external=True)

    def test_upgrade(self, app, api):
        with app.test_request_context():
            res = api.post(url_for("api_root.upgrade"))

            assert res.status_code == 499
            assert b"read-only mode" in res.data

    def test_plugins(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("plugins.all"))

            assert res.status_code == 200
            assert "extractors" in res.json

    def test_plugins_add(self, app, api):
        with app.test_request_context():
            res = api.post(
                url_for("plugins.add"),
                json={"plugin_type": "extractors", "name": "tap-gitlab"},
            )

            assert res.status_code == 499
            assert b"read-only mode" in res.data


@pytest.mark.usefixtures("seed_users")
class TestAuthenticationEnabled:
    @pytest.fixture(scope="class")
    def app(self, create_app):
        monkeypatch = MonkeyPatch()
        monkeypatch.setitem(
            ProjectSettingsService.config_override, "ui.authentication", True
        )

        yield create_app()

        monkeypatch.undo()

    @mock.patch("gitlab.Gitlab", return_value=gitlab_client())
    def test_gitlab_token_identity_creates_user(self, gitlab, app):
        token = {
            "access_token": "thisisavalidtoken",
            "id_token": "thisisavalidJWT",
            "created_at": 1548789020,
        }

        # test automatic user creation
        with app.test_request_context("/oauth/authorize"):
            identity = gitlab_token_identity(token)

            assert (
                db.session.query(OAuth)
                .options(joinedload(OAuth.user))
                .filter(
                    OAuth.access_token == token["access_token"]
                    and OAuth.id_token == token["id_token"]
                    and OAuth.provider_user_id == user.id
                    and OAuth.provider_id == "gitlab"
                    and User.email == user.email
                )
                .first()
            )

    @mock.patch("gitlab.Gitlab", return_value=gitlab_client())
    def test_gitlab_token_identity_maps_user(self, gitlab, app):
        token = {
            "access_token": "thisisavalidtoken",
            "id_token": "thisisavalidJWT",
            "created_at": 1548789020,
        }

        # test automatic user mapping
        with app.test_request_context("/oauth/authorize"):
            # let's create a user with the same email, that is currently logged
            user = users.create_user(email="valid@test.com")

            # but only if the user is currently logged (to prevent hi-jacking)
            with pytest.raises(OAuthError):
                identity = gitlab_token_identity(token)

            # the new identity should be mapped to the existing user
            login_user(user)
            identity = gitlab_token_identity(token)
            assert identity.user == user

    @freeze_time("2000-01-01")
    def test_login_audit_columns(self, app):
        with app.test_request_context():
            alice = users.get_user("alice")
            login_count = alice.login_count

            login_user(alice)

            # time is frozen, so it should work
            assert alice.last_login_at == datetime.utcnow()
            assert alice.login_count == login_count + 1

    def test_current_user(self, app):
        with app.test_request_context("/"):
            assert isinstance(current_user._get_current_object(), AnonymousUser)

    def test_identity(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("api_root.identity"))

            assert res.status_code == 401
            assert res.data == b"Authentication is required to access this resource."

    def test_identity_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("api_root.identity"))

                assert res.status_code == 200
                assert res.json["username"] == "alice"
                assert res.json["anonymous"] == False
                assert res.json["can_sign_in"] == False

    def test_bootstrap(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("root.bootstrap"))

            assert res.status_code == 302
            assert res.location.startswith(url_for("security.login", _external=True))

    def test_bootstrap_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("root.bootstrap"))

                assert res.status_code == 302
                assert res.location == url_for("root.default", _external=True)

    def test_upgrade(self, app, api):
        with app.test_request_context():
            res = api.post(url_for("api_root.upgrade"))

            assert res.status_code == 401
            assert res.data == b"Authentication is required to access this resource."

    def test_upgrade_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.post(url_for("api_root.upgrade"))

                assert res.status_code == 201
                assert res.data == b"Meltano update in progress."

    def test_plugins(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("plugins.all"))

            assert res.status_code == 401
            assert res.data == b"Authentication is required to access this resource."

    def test_plugins_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("plugins.all"))

                assert res.status_code == 200
                assert "extractors" in res.json

    def test_plugins_add(self, app, api):
        with app.test_request_context():
            res = api.post(
                url_for("plugins.add"),
                json={"plugin_type": "extractors", "name": "tap-gitlab"},
            )

            assert res.status_code == 401
            assert res.data == b"Authentication is required to access this resource."

    def test_plugins_add_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.post(
                    url_for("plugins.add"),
                    json={"plugin_type": "extractors", "name": "tap-gitlab"},
                )

                assert res.status_code == 200
                assert res.json["name"] == "tap-gitlab"

    def test_get_embed_unauthenticated(self, app, api):
        with app.test_request_context():
            with mock.patch(
                "meltano.api.controllers.embeds_helper.EmbedsHelper.get_embed_from_token",
                return_value={"result": "true"},
            ):
                res = api.get(url_for("embeds.get_embed", token="mytoken"))

                assert res.status_code == 200

    def test_get_embed_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with mock.patch(
                "meltano.api.controllers.embeds_helper.EmbedsHelper.get_embed_from_token",
                return_value={"result": "true"},
            ):
                with impersonate(users.get_user("alice")):
                    res = api.get(url_for("embeds.get_embed", token="mytoken"))

                    assert res.status_code == 200

    def test_create_embed_unauthenticated(self, app, api):
        with app.test_request_context():
            with mock.patch(
                "meltano.api.controllers.embeds",
                return_value={"result": "embedsnippet"},
            ):
                res = api.post(url_for("embeds.embed"))

                assert res.status_code == 401

    def test_create_embed_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with mock.patch(
                "meltano.api.controllers.embeds",
                return_value={"result": "embedsnippet"},
            ):
                with impersonate(users.get_user("alice")):
                    res = api.post(
                        url_for("embeds.embed"),
                        json={"resource_id": "test", "resource_type": "report"},
                    )

                    assert res.status_code == 200


@pytest.mark.usefixtures("seed_users")
class TestAuthenticationAndReadonlyEnabled:
    @pytest.fixture(scope="class")
    def app(self, create_app):
        monkeypatch = MonkeyPatch()

        config_override = ProjectSettingsService.config_override
        monkeypatch.setitem(config_override, "ui.authentication", True)
        monkeypatch.setitem(config_override, "ui.readonly", True)

        yield create_app()

        monkeypatch.undo()

    def test_current_user(self, app):
        with app.test_request_context("/"):
            assert isinstance(current_user._get_current_object(), AnonymousUser)

    def test_identity(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("api_root.identity"))

            assert res.status_code == 401
            assert res.data == b"Authentication is required to access this resource."

    def test_identity_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("api_root.identity"))

                assert res.status_code == 200
                assert res.json["username"] == "alice"
                assert res.json["anonymous"] == False
                assert res.json["can_sign_in"] == False

    def test_bootstrap(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("root.bootstrap"))

            assert res.status_code == 302
            assert res.location.startswith(url_for("security.login", _external=True))

    def test_bootstrap_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("root.bootstrap"))

                assert res.status_code == 302
                assert res.location == url_for("root.default", _external=True)

    def test_upgrade(self, app, api):
        with app.test_request_context():
            res = api.post(url_for("api_root.upgrade"))

            assert res.status_code == 401
            assert res.data == b"Authentication is required to access this resource."

    def test_upgrade_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.post(url_for("api_root.upgrade"))

                assert res.status_code == 499
                assert b"read-only mode" in res.data

    def test_plugins(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("plugins.all"))

            assert res.status_code == 401
            assert res.data == b"Authentication is required to access this resource."

    def test_plugins_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("plugins.all"))

                assert res.status_code == 200
                assert "extractors" in res.json

    def test_plugins_add(self, app, api):
        with app.test_request_context():
            res = api.post(
                url_for("plugins.add"),
                json={"plugin_type": "extractors", "name": "tap-gitlab"},
            )

            assert res.status_code == 401
            assert res.data == b"Authentication is required to access this resource."

    def test_plugins_add_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.post(
                    url_for("plugins.add"),
                    json={"plugin_type": "extractors", "name": "tap-gitlab"},
                )

                assert res.status_code == 499
                assert b"read-only mode" in res.data


@pytest.mark.usefixtures("seed_users")
class TestAuthenticationAndAnonymousReadonlyEnabled:
    @pytest.fixture(scope="class")
    def app(self, create_app):
        monkeypatch = MonkeyPatch()

        config_override = ProjectSettingsService.config_override
        monkeypatch.setitem(config_override, "ui.authentication", True)
        monkeypatch.setitem(config_override, "ui.anonymous_readonly", True)

        yield create_app()

        monkeypatch.undo()

    def test_current_user(self, app):
        with app.test_request_context("/"):
            assert isinstance(current_user._get_current_object(), AnonymousUser)

    def test_identity(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("api_root.identity"))

            assert res.status_code == 200
            assert res.json["anonymous"] == True
            assert res.json["can_sign_in"] == True

    def test_identity_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("api_root.identity"))

                assert res.status_code == 200
                assert res.json["username"] == "alice"
                assert res.json["anonymous"] == False
                assert res.json["can_sign_in"] == False

    def test_bootstrap(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("root.bootstrap"))

            assert res.status_code == 302
            assert res.location == url_for("root.default", _external=True)

    def test_bootstrap_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("root.bootstrap"))

                assert res.status_code == 302
                assert res.location == url_for("root.default", _external=True)

    def test_upgrade(self, app, api):
        with app.test_request_context():
            res = api.post(url_for("api_root.upgrade"))

            assert res.status_code == 403
            assert res.data == b"You do not have the required permissions."

    def test_upgrade_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.post(url_for("api_root.upgrade"))

                assert res.status_code == 201
                assert res.data == b"Meltano update in progress."

    def test_plugins(self, app, api):
        with app.test_request_context():
            res = api.get(url_for("plugins.all"))

            assert res.status_code == 200
            assert "extractors" in res.json

    def test_plugins_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.get(url_for("plugins.all"))

                assert res.status_code == 200
                assert "extractors" in res.json

    def test_plugins_add(self, app, api):
        with app.test_request_context():
            res = api.post(
                url_for("plugins.add"),
                json={"plugin_type": "extractors", "name": "tap-gitlab"},
            )

            assert res.status_code == 499
            assert b"read-only mode until you sign in" in res.data

    def test_plugins_add_authenticated(self, app, api, impersonate):
        with app.test_request_context():
            with impersonate(users.get_user("alice")):
                res = api.post(
                    url_for("plugins.add"),
                    json={"plugin_type": "extractors", "name": "tap-gitlab"},
                )

                assert res.status_code == 200
                assert res.json["name"] == "tap-gitlab"