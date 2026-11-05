from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

import typer

from quantumco.bootstrap.identity import build_mailer, sender_from
from quantumco.bootstrap.road_network import build_snapshot_use_case
from quantumco.bootstrap.settings import Settings, load_env_file
from quantumco.bootstrap.syntax_analysis import run_analysis_use_case, run_scenario_use_case
from quantumco.identity.domain.email import EmailAddress, EmailMessage
from quantumco.identity.infrastructure.resend_mailer import ResendMailer, RestrictedApiKeyError
from quantumco.platform.postgres import migrate
from quantumco.road_network.domain.highway_filter import FilterVariant
from quantumco.syntax_analysis.domain.edits import AddStreet, Edit, RemoveLink

app = typer.Typer(help="quantumco: mapa sintático aberto de Brusque-SC", no_args_is_help=True)
snapshot_app = typer.Typer(
    help="Rede Viária: cold start e reprocessamento do snapshot do OSM", no_args_is_help=True
)
app.add_typer(snapshot_app, name="snapshot")
scenario_app = typer.Typer(
    help='Cenários "e se…" (laboratório): edite a rede e compare', no_args_is_help=True
)
app.add_typer(scenario_app, name="scenario")
db_app = typer.Typer(help="Banco (PostGIS)", no_args_is_help=True)
app.add_typer(db_app, name="db")
analysis_app = typer.Typer(
    help="Análise Sintática: integração e escolha angulares", no_args_is_help=True
)
app.add_typer(analysis_app, name="analysis")
mail_app = typer.Typer(help="E-mail transacional (Resend)", no_args_is_help=True)
app.add_typer(mail_app, name="mail")

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


@app.callback()
def main(
    ctx: typer.Context,
    log_level: Annotated[
        str | None, typer.Option(help="DEBUG, INFO, WARNING (padrão: QC_LOG_LEVEL ou INFO)")
    ] = None,
) -> None:
    load_env_file()
    settings = Settings.from_env()
    level = (log_level or settings.log_level).upper()
    if level not in _LEVELS:
        raise typer.BadParameter(f"nível de log inválido: {level}")
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
    )
    # bibliotecas de terceiros só aparecem em DEBUG
    third_party = logging.DEBUG if level == "DEBUG" else logging.WARNING
    for noisy in ("httpx", "httpcore", "pyogrio", "fiona"):
        logging.getLogger(noisy).setLevel(third_party)
    ctx.obj = settings


def _migrate_if_configured(settings: Settings) -> None:
    applied = migrate(settings.require_database())
    if applied:
        typer.echo(f"migrações aplicadas: {', '.join(applied)}")


@db_app.command("migrate")
def db_migrate(ctx: typer.Context) -> None:
    """Aplica as migrações pendentes no PostGIS (QC_DATABASE_URL)."""
    settings: Settings = ctx.obj
    applied = migrate(settings.require_database())
    typer.echo(f"migrações aplicadas: {', '.join(applied) or 'nenhuma (já atualizado)'}")


@snapshot_app.command("build")
def build(
    ctx: typer.Context,
    variant: Annotated[FilterVariant, typer.Option(help="variante do filtro")] = (
        FilterVariant.BASE
    ),
    as_of: Annotated[
        datetime | None, typer.Option(help="data do extrato (consulta attic do Overpass)")
    ] = None,
) -> None:
    """Baixa o OSM, filtra, monta a topologia e grava o snapshot com manifesto."""
    settings: Settings = ctx.obj
    _migrate_if_configured(settings)
    result = build_snapshot_use_case(settings, as_of)(variant)
    report = result.snapshot.report
    typer.echo(f"snapshot {result.snapshot.snapshot_id} → {result.location}")
    typer.echo(f"  OSM base:        {result.snapshot.osm_base_timestamp.isoformat()}")
    typer.echo(f"  vias recebidas:  {report.ways_received}  aceitas: {report.ways_accepted}")
    typer.echo(
        f"  links mantidos:  {report.links_kept}  "
        f"desconectados: {report.links_excluded_disconnected} "
        f"({report.component_count} componentes)"
    )
    typer.echo(
        f"  extensão:        {report.length_kept_m / 1000:.1f} km mantidos, "
        f"{report.length_excluded_m / 1000:.1f} km excluídos"
    )


@analysis_app.command("run")
def analysis_run(ctx: typer.Context) -> None:
    """Calcula NAIN e NACH em todos os raios sobre o snapshot mais recente."""
    settings: Settings = ctx.obj
    _migrate_if_configured(settings)
    result, location = run_analysis_use_case(settings)()
    manifest = result.manifest
    typer.echo(f"análise → {location}")
    typer.echo(
        f"  {manifest['links']} trechos, {manifest['pieces']} retas, "
        f"motor {manifest['engine']} {manifest['engine_version']} "
        f"({manifest['engine_seconds']}s)"
    )
    if manifest["preliminary"]:
        typer.echo("  PRELIMINAR: equivalência com o depthmapX ainda não validada no CI")


@app.command("coldstart")
def coldstart(ctx: typer.Context) -> None:
    """Cold start completo: snapshot do OSM + análise sintática."""
    settings: Settings = ctx.obj
    _migrate_if_configured(settings)
    result = build_snapshot_use_case(settings)(FilterVariant.BASE)
    typer.echo(f"snapshot → {result.location}")
    analysis, location = run_analysis_use_case(settings)()
    typer.echo(f"análise → {location} ({analysis.manifest['engine_seconds']}s de motor)")


def _parse_street(spec: str, crs_epsg: int) -> AddStreet:
    from pyproj import Transformer  # noqa: PLC0415

    to_crs = Transformer.from_crs(4326, crs_epsg, always_xy=True)
    points = []
    for pair in spec.split(";"):
        lon, lat = (float(v) for v in pair.split(","))
        x, y = to_crs.transform(lon, lat)
        points.append((float(x), float(y)))
    return AddStreet(coords=tuple(points))


@scenario_app.command("run")
def scenario_run(
    ctx: typer.Context,
    name: Annotated[str, typer.Option(help="nome do cenário (ex.: ponte-centro)")],
    remove: Annotated[
        list[str] | None, typer.Option(help="id do trecho a remover (repetível)")
    ] = None,
    add: Annotated[
        list[str] | None,
        typer.Option(help='rua nova "lon,lat;lon,lat;…" (repetível; pontas encaixam na rede)'),
    ] = None,
    snap: Annotated[float, typer.Option(help="distância máxima de encaixe, em metros")] = 30.0,
) -> None:
    """Aplica as edições, recalcula a cidade inteira e compara com a análise publicada."""
    settings: Settings = ctx.obj
    _migrate_if_configured(settings)
    edits: list[Edit] = [RemoveLink(link_id) for link_id in remove or []]
    edits += [_parse_street(spec, 31982) for spec in add or []]
    result, location = run_scenario_use_case(settings, snap)(name, edits)
    typer.echo(f"cenário → {location}")
    for key, change in result.manifest["summary_result_zone"].items():
        typer.echo(
            f"  {key:9s} subiu de classe: {change['km_up']:7.2f} km   "
            f"caiu: {change['km_down']:7.2f} km"
        )
    typer.echo("  ver no mapa: /?cenario=" + name)


@scenario_app.command("list")
def scenario_list(ctx: typer.Context) -> None:
    """Lista os cenários gravados."""
    from quantumco.bootstrap.syntax_analysis import scenario_query  # noqa: PLC0415

    settings: Settings = ctx.obj
    for item in scenario_query(settings).list():
        typer.echo(
            f"{item['name']:30s} {item['created_at'][:16]}  "
            f"-{len(item['removed'])} +{len(item['added'])}"
        )


@app.command("serve")
def serve(
    host: Annotated[str, typer.Option(help="endereço")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="porta")] = 8000,
    reload: Annotated[bool, typer.Option(help="recarregar ao editar o código (dev)")] = False,
) -> None:
    """Sobe a API HTTP."""
    import uvicorn  # noqa: PLC0415 - só quem sobe o servidor precisa do uvicorn

    uvicorn.run(
        "quantumco.entrypoints.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


@mail_app.command("check")
def mail_check(ctx: typer.Context) -> None:
    """Confere a chave do Resend e se o domínio do remetente está verificado. Não envia nada."""
    settings: Settings = ctx.obj
    sender = sender_from(settings)
    typer.echo(f"remetente: {sender.formatted()}")
    if not settings.resend_api_key:
        typer.echo("RESEND_API_KEY vazio: e-mails só vão para o log (modo dev).")
        raise typer.Exit(1)
    mailer = ResendMailer(api_key=settings.resend_api_key, sender=sender)
    try:
        status = mailer.domain_status(sender.address.domain)
    except RestrictedApiKeyError:
        typer.echo(
            "chave OK, com permissão só de envio (bom para produção). Ela não consegue consultar "
            "domínios; para validar o remetente de ponta a ponta use `quantumco mail test`."
        )
        return
    if status is None:
        typer.echo(f"domínio {sender.address.domain} NÃO está cadastrado no Resend.")
        raise typer.Exit(1)
    typer.echo(f"domínio {sender.address.domain}: {status}")
    if status != "verified":
        raise typer.Exit(1)


@mail_app.command("test")
def mail_test(
    ctx: typer.Context,
    to: Annotated[str | None, typer.Option(help="destinatário (padrão: OWNER_EMAIL)")] = None,
) -> None:
    """Envia um e-mail de teste."""
    settings: Settings = ctx.obj
    recipient = to or settings.owner_email
    if not recipient:
        raise typer.BadParameter("informe --to ou defina OWNER_EMAIL")
    message = EmailMessage(
        to=(EmailAddress(recipient),),
        subject="quantumco: teste de envio",
        text=(
            "Este é um e-mail de teste do quantumco (mapa sintático aberto de Brusque).\n"
            "Se chegou, o envio via Resend está configurado."
        ),
    )
    message_id = build_mailer(settings).send(message)
    typer.echo(f"enviado: {message_id}")


if __name__ == "__main__":
    app()
