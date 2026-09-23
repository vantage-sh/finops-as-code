defmodule TwilioOnboarding.MixProject do
  use Mix.Project

  def project do
    [
      app: :twilio_onboarding,
      version: "0.1.0",
      elixir: "~> 1.18",
      description: "Local, reviewed Twilio subaccount onboarding for Vantage Livebooks.",
      package: [
        licenses: ["MIT"],
        files: ["lib", "mix.exs", "README.md", "LICENSE"],
        links: %{"Source" => "https://github.com/vantage-sh/finops-as-code/tree/main/livebook/twilio-subaccounts"}
      ],
      compilers: [:boundary] ++ Mix.compilers(),
      boundary: [default: [check: [apps: [:req, :kino, :jason]]]],
      deps: deps(),
      dialyzer: [plt_add_apps: [:mix]],
      aliases: [check: ["format --check-formatted", "compile --warnings-as-errors", "test", "credo --strict"]]
    ]
  end

  def application, do: [extra_applications: [:logger, :crypto]]

  def cli, do: [preferred_envs: [check: :test]]

  defp deps do
    [
      {:req, "== 0.7.4"},
      {:kino, "== 0.19.1"},
      {:jason, "~> 1.4"},
      {:boundary, "~> 0.10.4", runtime: false},
      {:credo, "~> 1.7", only: [:dev, :test], runtime: false},
      {:dialyxir, "~> 1.4", only: [:dev, :test], runtime: false},
      {:plug, "~> 1.18", only: :test},
      {:styler, "~> 1.11", only: [:dev, :test], runtime: false}
    ]
  end
end
