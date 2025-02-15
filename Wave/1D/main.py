import sys

sys.path.append(".")
from network import DNN
import numpy as np
import torch
from torch.autograd import grad
from pyDOE import lhs

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

# Parameters
x_min = 0
x_max = 1
t_min = 0
t_max = 1

ub = np.array([x_max, t_max])
lb = np.array([x_min, t_min])

N_u = 50
N_f = 10000


## IC , u(x,0) = 0
x_0 = np.random.uniform(x_min, x_max, (N_u, 1))
t_0 = np.zeros((N_u, 1))
xt_0 = np.hstack([x_0, t_0])
u_0 = np.zeros((N_u, 1))
u_t_0 = np.zeros((N_u, 1))

# BC : Controlled end points, u(x,0) = sin(2pi * t * freq), u(x, L) = 0
x_bc1 = np.zeros((N_u, 1))
t_bc1 = np.random.uniform(t_min, t_max, (N_u, 1))
u_bc1 = np.sin(2 * np.pi * t_bc1 * 2)

x_bc2 = np.ones((N_u, 1)) * x_max
t_bc2 = np.random.uniform(t_min, t_max, (N_u, 1))
u_bc2 = np.zeros((N_u, 1))

x_bc = np.vstack([x_bc1, x_bc2])
t_bc = np.vstack([t_bc1, t_bc2])
xt_bc = np.hstack([x_bc, t_bc])
u_bc = np.vstack((u_bc1, u_bc2))

# collocation points
x_f = x_min + (x_max - x_min) * lhs(1, N_f)
t_f = t_min + (t_max - t_min) * lhs(1, N_f)
x_f = np.vstack([x_0, x_bc, x_f])
t_f = np.vstack([t_0, t_bc, t_f])


xt_0 = torch.tensor(xt_0, dtype=torch.float32).to(device)
u_0 = torch.tensor(u_0, dtype=torch.float32).to(device)
u_t_0 = torch.tensor(u_t_0, dtype=torch.float32).to(device)

xt_bc = torch.tensor(xt_bc, dtype=torch.float32).to(device)
u_bc = torch.tensor(u_bc, dtype=torch.float32).to(device)

x_f = torch.tensor(x_f, dtype=torch.float32).to(device)
t_f = torch.tensor(t_f, dtype=torch.float32).to(device)
xt_f = torch.hstack([x_f, t_f])


class PINN:
    c = 1

    def __init__(self) -> None:
        self.net = DNN(dim_in=2, dim_out=1, n_layer=5, n_node=20, ub=ub, lb=lb).to(
            device
        )
        self.optimizer = torch.optim.LBFGS(
            self.net.parameters(),
            lr=1.0,
            max_iter=50000,
            max_eval=50000,
            history_size=50,
            tolerance_grad=1e-5,
            tolerance_change=1.0 * np.finfo(float).eps,
            line_search_fn="strong_wolfe",
        )
        self.ms = lambda x: torch.mean(torch.square(x))
        self.iter = 0

    def loss_ic(self, xt):
        xt = xt.clone()
        xt.requires_grad = True
        u = self.net(xt)

        u_t = grad(u.sum(), xt, create_graph=True)[0][:, 1:2]
        mse_0 = self.ms(u - u_0) + self.ms(u_t - u_t_0)
        return mse_0

    def loss_bc(self, xt):
        u = self.net(xt)
        mse_bc = self.ms(u - u_bc)
        return mse_bc

    def loss_pde(self, xt):
        xt = xt.clone()
        xt.requires_grad = True
        u = self.net(xt)

        u_xt = grad(u.sum(), xt, create_graph=True)[0]
        u_x = u_xt[:, 0:1]
        u_xx = grad(u_x.sum(), xt, create_graph=True)[0][:, 0:1]

        u_t = u_xt[:, 1:2]
        u_tt = grad(u_t.sum(), xt, create_graph=True)[0][:, 1:2]

        pde = u_tt - (self.c ** 2) * (u_xx)
        mse_pde = self.ms(pde)
        return mse_pde

    def closure(self):
        self.optimizer.zero_grad()

        mse_0 = self.loss_ic(xt_0)
        mse_bc = self.loss_bc(xt_bc)
        mse_pde = self.loss_pde(xt_f)

        # collocation points
        loss = mse_0 + mse_bc + mse_pde

        loss.backward()
        self.iter += 1
        print(
            f"\r{self.iter}, Loss : {loss.item():.5e}, ic : {mse_0:.3e}, bc : {mse_bc:.3e}, f : {mse_pde:.3e}",
            end="",
        )
        if self.iter % 500 == 0:
            torch.save(self.net.state_dict(), "./Wave/1D/weight.pt")
            print("")

        return loss


if __name__ == "__main__":
    pinn = PINN()
    pinn.optimizer.step(pinn.closure)
    torch.save(pinn.net.state_dict(), "./Wave/1D/weight.pt")
