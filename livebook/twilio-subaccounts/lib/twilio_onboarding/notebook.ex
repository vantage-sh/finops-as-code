defmodule TwilioOnboarding.Notebook do
  @moduledoc "Starts the local connection wizard without reading credentials or making requests."

  alias TwilioOnboarding.Notebook.Panel

  @doc "Render the wizard; discovery and writes require separate explicit actions."
  @spec start() :: :ok
  def start do
    Kino.render(Panel.new())
    :ok
  end
end
