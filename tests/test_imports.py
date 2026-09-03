def test_backend_packages_import() -> None:
    import agents
    import api
    import app
    import models
    import services
    import tools

    assert app.__version__ == "0.1.0"
    assert agents.__name__ == "agents"
    assert api.__name__ == "api"
    assert models.__name__ == "models"
    assert services.__name__ == "services"
    assert tools.__name__ == "tools"


def test_application_modules_import() -> None:
    from api.health import router
    from app.config import Settings, settings
    from app.database import check_database_connection, configured_dialect, get_engine
    from app.exceptions import AppError
    from app.main import app, create_app

    assert router is not None
    assert isinstance(settings, Settings)
    assert callable(get_engine)
    assert callable(check_database_connection)
    assert issubclass(AppError, Exception)
    assert create_app() is not None
    assert app.title == settings.app_name


def test_all_models_are_exported() -> None:
    from models import (
        AgentRun,
        Approval,
        Company,
        CostEntry,
        Customer,
        DailyMetric,
        DeliveryProject,
        Experiment,
        Lead,
        Report,
        RevenueEntry,
        Task,
    )

    expected_tables = {
        AgentRun: "agent_runs",
        Approval: "approvals",
        Company: "companies",
        CostEntry: "cost_entries",
        Customer: "customers",
        DailyMetric: "daily_metrics",
        DeliveryProject: "delivery_projects",
        Experiment: "experiments",
        Lead: "leads",
        Report: "reports",
        RevenueEntry: "revenue_entries",
        Task: "tasks",
    }

    for model, table_name in expected_tables.items():
        assert model.__tablename__ == table_name
